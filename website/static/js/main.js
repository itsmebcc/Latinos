// Latinos.org — Frontend JavaScript

document.addEventListener('DOMContentLoaded', function() {

    // === Dark mode toggle ===
    const darkToggle = document.getElementById('darkToggle');
    if (darkToggle) {
        // Check saved preference or system preference
        const saved = localStorage.getItem('darkMode');
        if (saved === 'true' || (saved === null && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.body.classList.add('dark');
        }
        darkToggle.addEventListener('click', function() {
            document.body.classList.toggle('dark');
            localStorage.setItem('darkMode', document.body.classList.contains('dark'));
        });
    }

    // === Mobile menu toggle ===
    const menuBtn = document.getElementById('mobileMenuBtn');
    const mainNav = document.getElementById('mainNav');

    if (menuBtn && mainNav) {
        menuBtn.addEventListener('click', function() {
            mainNav.classList.toggle('open');
            menuBtn.setAttribute('aria-expanded', mainNav.classList.contains('open') ? 'true' : 'false');
        });
    }

    // === Breaking news rotation ===
    const breakingItems = document.querySelectorAll('.breaking-item');
    if (breakingItems.length > 1) {
        let currentIdx = 0;
        setInterval(function() {
            breakingItems[currentIdx].classList.remove('active');
            currentIdx = (currentIdx + 1) % breakingItems.length;
            breakingItems[currentIdx].classList.add('active');
        }, 5000); // Rotate every 5 seconds
    }

    // === Close mobile menu when clicking outside ===
    document.addEventListener('click', function(e) {
        if (mainNav && mainNav.classList.contains('open')) {
            if (!mainNav.contains(e.target) && !menuBtn.contains(e.target)) {
                mainNav.classList.remove('open');
                menuBtn.setAttribute('aria-expanded', 'false');
            }
        }
    });

    // === Newsletter signup capture ===
    document.querySelectorAll('[data-newsletter-form]').forEach(function(form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            const message = form.parentElement.querySelector('.newsletter-message') || form.nextElementSibling;
            const data = new FormData(form);
            data.append('source', form.dataset.newsletterSource || 'footer');
            if (form.dataset.articleId) data.append('article_id', form.dataset.articleId);
            if (message) {
                message.textContent = 'Enviando...';
                message.className = 'newsletter-message is-loading';
            }
            try {
                const resp = await fetch('/api/newsletter', { method: 'POST', body: data });
                const payload = await resp.json();
                if (!payload.ok) throw new Error(payload.error || 'No se pudo registrar.');
                form.reset();
                if (message) {
                    message.textContent = payload.message || 'Gracias por suscribirte.';
                    message.className = 'newsletter-message is-ok';
                }
            } catch (err) {
                if (message) {
                    message.textContent = err.message || String(err);
                    message.className = 'newsletter-message is-error';
                }
            }
        });
    });

    // === Share click tracking ===
    document.querySelectorAll('[data-share-article]').forEach(function(link) {
        link.addEventListener('click', function() {
            const data = new FormData();
            data.append('network', link.dataset.shareNetwork || 'other');
            const url = `/api/share/${link.dataset.shareArticle}`;
            if (navigator.sendBeacon) {
                navigator.sendBeacon(url, data);
            } else {
                fetch(url, { method: 'POST', body: data, keepalive: true }).catch(function() {});
            }
        });
    });

});
