// Testy Timetables — onboarding
// Per-page row add/remove logic lives inline in teachers.html / leave.html
// so each template stays self-contained. This file is a hook for anything
// shared across all onboarding pages later (e.g. autosave, analytics).

document.addEventListener('DOMContentLoaded', function () {
    // Smooth-scroll to #tutorials from the welcome page's secondary link.
    document.querySelectorAll('a[href^="#"]').forEach(function (link) {
        link.addEventListener('click', function (e) {
            const target = document.querySelector(link.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });
});
