/**
 * Shared JavaScript for Manager Dashboard and Manager Reports pages.
 * Handles date validation, filtering, report export, and chart/tooltip initialization.
 */

/**
 * Validates that both start date and end date are provided,
 * and that start date is not after end date.
 * Displays validation error feedback in the UI element #dateValidationError.
 */
function validateDates(start, end) {
    const errorDiv = document.getElementById("dateValidationError");
    if (!errorDiv) return true;

    // Reset error state
    errorDiv.classList.add("d-none");
    errorDiv.innerText = "";

    if (!start || !end) {
        errorDiv.innerText = "Please select both Start Date and End Date.";
        errorDiv.classList.remove("d-none");
        return false;
    }

    if (new Date(start) > new Date(end)) {
        errorDiv.innerText = "Start Date cannot be later than End Date.";
        errorDiv.classList.remove("d-none");
        return false;
    }

    return true;
}

/**
 * Filters the current page or target URL based on selected date range.
 * Preserves the current page URL or accepts a custom targetUrl.
 */
function updateFilters(targetUrl) {
    const startInput = document.getElementById("startDate");
    const endInput = document.getElementById("endDate");

    if (!startInput || !endInput) return;

    const start = startInput.value;
    const end = endInput.value;

    if (validateDates(start, end)) {
        const url = targetUrl || window.location.pathname;
        window.location.href = `${url}?start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}`;
    }
}

/**
 * Directs the user browser to download reports in PDF or CSV formats.
 */
function exportReport(format, pdfUrl, csvUrl) {
    const startInput = document.getElementById("startDate");
    const endInput = document.getElementById("endDate");

    if (!startInput || !endInput) return;

    const start = startInput.value;
    const end = endInput.value;

    if (validateDates(start, end)) {
        let url = "";
        if (format === 'PDF') {
            url = pdfUrl || "/manager-reports/export/pdf/";
        } else if (format === 'CSV') {
            url = csvUrl || "/manager-reports/export/csv/";
        }

        if (url) {
            window.location.href = `${url}?start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}`;
        }
    }
}

/**
 * Initializes Bootstrap Tooltips for interactive elements (such as SVG data nodes).
 */
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.forEach(function (tooltipTriggerEl) {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

/**
 * Initializes chart-related features and tooltips.
 */
function initializeChart() {
    initializeTooltips();
}

// Auto-initialize tooltips and chart features on DOM content load
document.addEventListener("DOMContentLoaded", function () {
    initializeChart();
});
