// static/script.js
document.addEventListener("DOMContentLoaded", function () {
    console.log("Anime Tracker loaded.");

    // Get all anime marking forms
    const markingForms = document.querySelectorAll('form[action*="mark"]');

    markingForms.forEach(form => {
        // Add event listener for form submission
        form.addEventListener('submit', function (e) {
            // Prevent multiple submissions
            const buttons = form.querySelectorAll('button');
            buttons.forEach(button => {
                button.disabled = true;
            });

            // Log the form data for debugging
            const formData = new FormData(form);
            console.log("Submitting form data:");
            for (let [key, value] of formData.entries()) {
                console.log(`${key}: ${value.substring(0, 50)}${value.length > 50 ? '...' : ''}`);
            }

            // Let the form submit normally
            return true;
        });
    });

    // Fix for older browsers that might have issues with JSON in form values
    document.querySelectorAll('input[type="hidden"][name="anime"]').forEach(input => {
        // Ensure the value is properly set with valid JSON
        try {
            // Parse and re-stringify to ensure valid JSON
            const animeData = JSON.parse(input.value);
            // No need to update if it's already valid JSON
        } catch (e) {
            console.error("Invalid JSON in anime input:", e);
        }
    });
});