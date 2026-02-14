let videoEl = null;
let streamRef = null;

async function startCam(videoId) {
  videoEl = document.getElementById(videoId);
  if (!videoEl) return;
  try {
    streamRef = await navigator.mediaDevices.getUserMedia({ video: true });
    videoEl.srcObject = streamRef;
    videoEl.play();
  } catch (e) {
    console.error('Cannot start camera', e);
    alert('Cannot access camera: ' + e.message);
  }
}

function stopCam() {
  if (streamRef) {
    streamRef.getTracks().forEach(t => t.stop());
    streamRef = null;
  }
  if (videoEl) videoEl.pause();
}

