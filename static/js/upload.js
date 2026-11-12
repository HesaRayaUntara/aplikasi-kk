(() => {
    const fileInput = document.getElementById('file_kk');
    const form = document.getElementById('uploadForm');
    if (!fileInput || !form) return;

    const dropArea = document.getElementById('dropArea');
    const preview = document.getElementById('previewContainer');
    const previewImage = document.getElementById('imagePreview');
    const feedback = document.getElementById('uploadFeedback');
    const button = document.getElementById('uploadButton');
    const buttonText = document.getElementById('uploadButtonText');
    const allowedTypes = new Set(['image/jpeg', 'image/png']);
    const maxSize = 5 * 1024 * 1024;

    function showError(message) {
        feedback.textContent = message;
        feedback.classList.remove('hidden');
        feedback.focus?.();
    }

    function displayFile(file) {
        feedback.classList.add('hidden');
        if (!file) return;
        if (!allowedTypes.has(file.type)) {
            fileInput.value = '';
            preview.classList.add('hidden');
            showError('Format file harus JPG, JPEG, atau PNG.');
            return;
        }
        if (file.size > maxSize) {
            fileInput.value = '';
            preview.classList.add('hidden');
            showError('Ukuran gambar maksimal 5 MB.');
            return;
        }
        previewImage.src = URL.createObjectURL(file);
        document.getElementById('fileName').textContent = file.name;
        document.getElementById('fileSize').textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
        preview.classList.remove('hidden');
    }

    fileInput.addEventListener('change', () => displayFile(fileInput.files[0]));
    for (const eventName of ['dragenter', 'dragover']) {
        dropArea.addEventListener(eventName, event => {
            event.preventDefault();
            dropArea.classList.add('border-blue-500', 'bg-blue-50');
        });
    }
    for (const eventName of ['dragleave', 'drop']) {
        dropArea.addEventListener(eventName, event => {
            event.preventDefault();
            dropArea.classList.remove('border-blue-500', 'bg-blue-50');
        });
    }
    dropArea.addEventListener('drop', event => {
        const file = event.dataTransfer.files[0];
        if (!file) return;
        const transfer = new DataTransfer();
        transfer.items.add(file);
        fileInput.files = transfer.files;
        displayFile(file);
    });
    form.addEventListener('submit', event => {
        if (!fileInput.files.length) {
            event.preventDefault();
            showError('Pilih gambar Kartu Keluarga sebelum melanjutkan.');
            return;
        }
        button.disabled = true;
        button.classList.add('cursor-wait', 'opacity-80');
        button.querySelector('[data-lucide]')?.remove();
        const spinner = document.createElement('span');
        spinner.className = 'h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white';
        button.prepend(spinner);
        buttonText.textContent = 'Sedang membaca gambar…';
        button.setAttribute('aria-live', 'polite');
    });
})();
