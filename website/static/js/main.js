// Latinos.org — Frontend JavaScript

document.addEventListener('DOMContentLoaded', function() {

    // === Mobile menu toggle ===
    const menuBtn = document.getElementById('mobileMenuBtn');
    const mainNav = document.getElementById('mainNav');

    if (menuBtn && mainNav) {
        menuBtn.addEventListener('click', function() {
            mainNav.classList.toggle('open');
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
            }
        }
    });

});
