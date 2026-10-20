// SDSU MicrobialDataSystem Platform
// Client-side interactions and download audit modal handling

let currentDatasetId = null;

function openDownloadModal(datasetId, title, sourceType) {
    currentDatasetId = datasetId;
    const modal = document.getElementById('downloadModal');
    const modalTitle = document.getElementById('modalDatasetTitle');
    const sourceInfo = document.getElementById('modalSourceType');
    
    if (modalTitle) modalTitle.innerText = title;
    if (sourceInfo) {
        sourceInfo.innerText = sourceType === 'github' ? 'GitHub Repository / Direct Stream' : 'SDSU Server Local/Cloud Storage';
    }
    
    if (modal) {
        modal.classList.add('active');
    }
}

function closeDownloadModal() {
    const modal = document.getElementById('downloadModal');
    if (modal) {
        modal.classList.remove('active');
    }
    currentDatasetId = null;
}

// Submit download tracking telemetry and trigger download
async function submitDownloadTracking(event) {
    if (event) event.preventDefault();
    if (!currentDatasetId) return;

    const institution = document.getElementById('modalInstitution')?.value || 'Unspecified Institution';
    const purpose = document.getElementById('modalPurpose')?.value || 'Academic Research';
    const submitBtn = document.getElementById('modalSubmitBtn');

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = 'Registering & Dispatching...';
    }

    try {
        const response = await fetch(`/dataset/${currentDatasetId}/download`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                institution: institution,
                purpose: purpose
            })
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            closeDownloadModal();
            // Trigger download or repository view
            window.location.href = result.download_url;
            
            // Refresh counter if present
            const countEl = document.getElementById(`dl-count-${currentDatasetId}`);
            if (countEl) {
                const cur = parseInt(countEl.innerText) || 0;
                countEl.innerText = cur + 1;
            }
        } else {
            alert(result.message || 'Error processing download request.');
        }
    } catch (err) {
        console.error('Download tracking error:', err);
        alert('Network communication error, please try again.');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerText = 'Confirm Purpose & Start Download';
        }
    }
}

// Close modal when clicking backdrop
window.addEventListener('click', function(e) {
    const modal = document.getElementById('downloadModal');
    if (e.target === modal) {
        closeDownloadModal();
    }
});
