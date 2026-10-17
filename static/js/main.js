// SDSU CLM-Microbe Data Platform
// Client-side interactions and download audit modal handling

let currentDatasetId = null;

function openDownloadModal(datasetId, title, sourceType) {
    currentDatasetId = datasetId;
    const modal = document.getElementById('downloadModal');
    const modalTitle = document.getElementById('modalDatasetTitle');
    const sourceInfo = document.getElementById('modalSourceType');
    
    if (modalTitle) modalTitle.innerText = title;
    if (sourceInfo) {
        sourceInfo.innerText = sourceType === 'github' ? 'GitHub 远端仓库 / Release' : 'SDSU 本地服务器存储归档';
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

// 提交下载审计登记并触发分发
async function submitDownloadTracking(event) {
    if (event) event.preventDefault();
    if (!currentDatasetId) return;

    const institution = document.getElementById('modalInstitution')?.value || '未注明单位';
    const purpose = document.getElementById('modalPurpose')?.value || 'Academic Research';
    const submitBtn = document.getElementById('modalSubmitBtn');

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = '正在记录并分发...';
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
            // 在新标签页或当前页面触发下载
            window.location.href = result.download_url;
            
            // 稍后刷新当前下载计数显示（如果有）
            const countEl = document.getElementById(`dl-count-${currentDatasetId}`);
            if (countEl) {
                const cur = parseInt(countEl.innerText) || 0;
                countEl.innerText = cur + 1;
            }
        } else {
            alert(result.message || '下载处理遇到问题，请重试');
        }
    } catch (err) {
        console.error('Download tracking error:', err);
        alert('网络通信异常，请重试');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerText = '确认用途并开始下载';
        }
    }
}

// 点击模态框背景关闭
window.addEventListener('click', function(e) {
    const modal = document.getElementById('downloadModal');
    if (e.target === modal) {
        closeDownloadModal();
    }
});
