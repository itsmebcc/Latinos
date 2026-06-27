// Latinos.org Admin — Frontend JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss success alerts after 3 seconds
    const alerts = document.querySelectorAll('.alert-success');
    alerts.forEach(a => setTimeout(() => a.style.opacity = '0', 3000));
});
