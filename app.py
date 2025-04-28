import os
import re
import requests
import base64
from flask import Flask, request, jsonify, render_template, Response
from dotenv import load_dotenv # Optional: for API Key

load_dotenv() # Optional: Load environment variables from .env file

app = Flask(__name__)

# Optional: Use GitHub PAT for higher rate limits
GITHUB_TOKEN = os.getenv('GITHUB_PAT') # Create a .env file with GITHUB_PAT=your_token
HEADERS = {'Accept': 'application/vnd.github.v3+json'}
if GITHUB_TOKEN:
    HEADERS['Authorization'] = f'token {GITHUB_TOKEN}'
    print("Using GitHub Personal Access Token.")
else:
    print("Warning: No GitHub PAT found. Using unauthenticated requests (lower rate limit).")


def parse_github_url(url):
    """Extracts owner and repo name from various GitHub URL formats."""
    patterns = [
        r"https?://github\.com/([^/]+)/([^/]+)/?.*",  # Standard https
        r"git@github\.com:([^/]+)/([^/]+)\.git",      # SSH
    ]
    for pattern in patterns:
        match = re.match(pattern, url)
        if match:
            owner, repo = match.groups()
            # Remove optional .git suffix if present
            if repo.endswith('.git'):
                repo = repo[:-4]
            return owner, repo
    return None, None

def get_default_branch(owner, repo):
    """Gets the default branch name for a repository."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        response = requests.get(api_url, headers=HEADERS)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json().get('default_branch', 'main') # Default to 'main' if not found
    except requests.exceptions.RequestException as e:
        print(f"Error fetching repo info: {e}")
        return None # Indicate error

def get_repo_files(owner, repo, branch):
    """Fetches all file paths and their blob URLs recursively using the Git Trees API."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    all_files = []
    try:
        response = requests.get(api_url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()

        if data.get("truncated"):
             print(f"Warning: File tree for {owner}/{repo} is truncated. Some files may be missing.")
             # Handling truncated results is more complex, often requiring multiple API calls.
             # For this example, we'll proceed with the truncated list.

        tree = data.get('tree', [])
        for item in tree:
            if item['type'] == 'blob': # We only care about files (blobs)
                all_files.append({'path': item['path'], 'url': item['url']})
        return all_files
    except requests.exceptions.RequestException as e:
        print(f"Error fetching file tree: {e}")
        return None # Indicate error
    except Exception as e:
        print(f"Error processing file tree data: {e}")
        return None


def get_file_content(url):
    """Fetches and decodes the content of a specific file blob."""
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        blob_data = response.json()

        if blob_data.get('encoding') == 'base64':
            content_bytes = base64.b64decode(blob_data['content'])
            try:
                # Attempt to decode as UTF-8, skip if it fails (likely binary)
                return content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                print(f"Skipping binary file (or non-UTF-8 content) at {url}")
                return None # Indicate skippable content
        else:
            # Handle other potential encodings if necessary, or just skip
            print(f"Skipping file with unsupported encoding '{blob_data.get('encoding')}' at {url}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching file content for {url}: {e}")
        return None # Indicate error fetching this specific file
    except Exception as e:
        print(f"Error processing file content for {url}: {e}")
        return None


@app.route('/')
def index():
    """Renders the main HTML page."""
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_repo():
    """API endpoint to handle the conversion request."""
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "Missing 'url' in request body"}), 400

    repo_url = data['url']
    owner, repo = parse_github_url(repo_url)

    if not owner or not repo:
        return jsonify({"error": "Invalid GitHub repository URL format."}), 400

    print(f"Processing repository: {owner}/{repo}")

    default_branch = get_default_branch(owner, repo)
    if not default_branch:
         return jsonify({"error": f"Could not determine default branch for {owner}/{repo}. Repo might be private, non-existent, or API error occurred."}), 404

    print(f"Using default branch: {default_branch}")

    files_to_process = get_repo_files(owner, repo, default_branch)
    if files_to_process is None: # Check if None was returned due to an error
         return jsonify({"error": f"Could not fetch file list for {owner}/{repo}. Check permissions or API rate limits."}), 500
    if not files_to_process:
         return jsonify({"error": f"Repository {owner}/{repo} appears to be empty or no files found."}), 404

    print(f"Found {len(files_to_process)} files to process.")

    markdown_content = []
    markdown_content.append(f"# Codebase for {owner}/{repo}\n\n")

    processed_count = 0
    skipped_count = 0

    for file_info in files_to_process:
        file_path = file_info['path']
        blob_url = file_info['url']
        print(f"  Processing: {file_path}...")

        content = get_file_content(blob_url)

        if content is not None:
            # Remove blank lines (lines containing only whitespace)
            lines = content.splitlines()
            non_blank_lines = [line for line in lines if line.strip()]
            processed_content = '\n'.join(non_blank_lines)

            # Add to markdown output
            markdown_content.append(f"## `{file_path}`\n") # Use backticks for filename
            markdown_content.append("```") # Start code block
            # Optional: Add language hint based on extension (more complex)
            # ext = os.path.splitext(file_path)[1].lower().strip('.')
            # markdown_content.append(f"```{ext}")
            markdown_content.append(processed_content)
            markdown_content.append("```\n")
            markdown_content.append("---\n") # Separator
            processed_count += 1
        else:
            # File content was skipped (binary, decode error, fetch error)
            skipped_count += 1
            markdown_content.append(f"## `{file_path}`\n")
            markdown_content.append(f"*Content skipped (binary, non-UTF8, or error fetching).*\n")
            markdown_content.append("---\n")

    final_markdown = "\n".join(markdown_content)
    print(f"Conversion complete. Processed: {processed_count}, Skipped: {skipped_count}")

    # Return as plain text for the frontend to handle blob creation
    return Response(final_markdown, mimetype='text/markdown')
    # Alternative: Return JSON with content
    # return jsonify({"markdown": final_markdown, "filename": f"{repo}_codebase.md"})


if __name__ == '__main__':
    # Use 0.0.0.0 to make it accessible on your network, useful for testing
    app.run(debug=True, host='0.0.0.0', port=10000)
    # For production, use a proper WSGI server like Gunicorn or Waitress
    # Example: gunicorn -w 4 app:app
