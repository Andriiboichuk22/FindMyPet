document.addEventListener('DOMContentLoaded', () => {
    setupMobileNav();
    setupFlashMessages();
    setupPhoneReveal();
    setupLightbox();
    setupConfirmForms();
});

function setupMobileNav() {
    const toggle = document.querySelector('.site-nav-toggle');
    const nav = document.getElementById('site-nav');
    if (!toggle || !nav) {
        return;
    }

    toggle.addEventListener('click', () => {
        const isOpen = nav.classList.toggle('is-open');
        toggle.classList.toggle('is-open', isOpen);
        toggle.setAttribute('aria-expanded', String(isOpen));
        document.body.classList.toggle('nav-open', isOpen);
    });

    nav.querySelectorAll('a').forEach((link) => {
        link.addEventListener('click', () => {
            nav.classList.remove('is-open');
            toggle.classList.remove('is-open');
            toggle.setAttribute('aria-expanded', 'false');
            document.body.classList.remove('nav-open');
        });
    });
}

function setupFlashMessages() {
    const messages = document.querySelectorAll('.flash-message');

    messages.forEach((message) => {
        window.setTimeout(() => {
            message.classList.add('is-hiding');
            window.setTimeout(() => message.remove(), 260);
        }, 4000);
    });
}

function setupPhoneReveal() {
    const phoneButtons = document.querySelectorAll('.reveal-phone-btn[data-phone]');

    phoneButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const phone = button.dataset.phone;
            if (!phone) {
                return;
            }

            button.textContent = phone;
            button.disabled = true;
        });
    });
}

function setupLightbox() {
    const lightbox = document.getElementById('lightbox');
    const lightboxImage = document.getElementById('lightbox-img');
    if (!lightbox || !lightboxImage) {
        return;
    }

    const closeButton = lightbox.querySelector('.close');
    const cardImages = document.querySelectorAll('.card img');

    const closeLightbox = () => {
        lightbox.style.display = 'none';
        lightboxImage.src = '';
    };

    cardImages.forEach((image) => {
        image.addEventListener('click', () => {
            lightboxImage.src = image.src;
            lightboxImage.alt = image.alt || 'Перегляд фото';
            lightbox.style.display = 'flex';
        });
    });

    if (closeButton) {
        closeButton.addEventListener('click', closeLightbox);
    }

    lightbox.addEventListener('click', (event) => {
        if (event.target === lightbox) {
            closeLightbox();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && lightbox.style.display === 'flex') {
            closeLightbox();
        }
    });
}

function setupConfirmForms() {
    const forms = document.querySelectorAll('form[data-confirm]');

    forms.forEach((form) => {
        form.addEventListener('submit', (event) => {
            const message = form.dataset.confirm || 'Підтвердьте дію.';
            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });
}
