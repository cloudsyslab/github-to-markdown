document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('repoForm');
    const repoUrlInput = document.getElementById('repoUrl');
    const submitBtn = document.getElementById('submitBtn');
    const statusDiv = document.getElementById('status');
    const downloadLink = document.getElementById('downloadLink');

    form.addEventListener('submit', async (event) => {
        event.preventDefault(); // Prevent default form submission

        const repoUrl = repoUrlInput.value.trim();
        if (!repoUrl) {
            setStatus('Please enter a GitHub repository URL.', true);
            return;
        }

        // Basic validation (can be improved)
        if (!repoUrl.includes('github.com/')) {
             setStatus('Please enter a valid GitHub repository URL.', true);
             return;
        }

        // Disable button and show loading state
        submitBtn.disabled = true;
        downloadLink.style.display = 'none'; // Hide previous link
        downloadLink.removeAttribute('href'); // Clear previous blob URL
        setStatus('Fetching repository data and converting...');

        try {
            const response = await fetch('/convert', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: repoUrl }),
            });

            if (!response.ok) {
                // Try to get error message from backend response
                let errorMsg = `Error: ${response.status} ${response.statusText}`;
                try {
                    const errorData = await response.json();
                    errorMsg = `Error: ${errorData.error || response.statusText}`;
                } catch (e) {
                    // If response is not JSON, use the status text
                    console.error("Could not parse error response as JSON", e);
                }
                 throw new Error(errorMsg);
            }

            // Get the markdown text directly from the response body
            const markdownContent = await response.text();

             // Extract repo name for filename (simple approach)
            let filename = "repository_codebase.md";
            try {
                const urlParts = new URL(repoUrl).pathname.split('/');
                const repoName = urlParts[2] ? urlParts[2].replace('.git', '') : 'repository';
                filename = `${repoName}_codebase.md`;
            } catch (e) {
                console.warn("Could not parse repo name from URL for filename.", e);
            }

            // Create a Blob from the markdown content
            const blob = new Blob([markdownContent], { type: 'text/markdown;charset=utf-8' });

            // Create a temporary URL for the Blob
            const blobUrl = URL.createObjectURL(blob);

            // Set up the download link
            downloadLink.href = blobUrl;
            downloadLink.download = filename; // Set the filename for download
            downloadLink.style.display = 'inline-block'; // Make the link visible

            setStatus('Conversion successful! Click the link below to download.', false);

        } catch (error) {
            console.error('Conversion failed:', error);
            setStatus(`Conversion failed: ${error.message}`, true);
        } finally {
            // Re-enable the button regardless of success or failure
            submitBtn.disabled = false;
        }
    });

    function setStatus(message, isError = false) {
        statusDiv.textContent = message;
        statusDiv.className = isError ? 'error' : ''; // Add error class if needed
    }

    // Clean up the Blob URL when the user navigates away or closes the tab
    // (Good practice, though browser garbage collection usually handles it)
    window.addEventListener('beforeunload', () => {
        const blobUrl = downloadLink.href;
        if (blobUrl && blobUrl.startsWith('blob:')) {
            URL.revokeObjectURL(blobUrl);
        }
    });
});