// Comic Book Collection Manager - JavaScript functionality

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Auto-hide alerts after 5 seconds
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            var bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // Form validation enhancement
    var forms = document.querySelectorAll('.needs-validation');
    Array.prototype.slice.call(forms).forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });

    // Search form enhancement
    var searchForm = document.getElementById('search');
    if (searchForm) {
        searchForm.addEventListener('input', function() {
            // Add debouncing for search
            clearTimeout(this.searchTimeout);
            this.searchTimeout = setTimeout(function() {
                // Auto-submit search after 500ms of no typing
                if (searchForm.value.length >= 3 || searchForm.value.length === 0) {
                    searchForm.form.submit();
                }
            }, 500);
        });
    }

    // Image preview for file uploads
    var fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(function(input) {
        input.addEventListener('change', function() {
            var file = this.files[0];
            if (file) {
                var reader = new FileReader();
                reader.onload = function(e) {
                    // Create preview if it doesn't exist
                    var preview = input.parentNode.querySelector('.image-preview');
                    if (!preview) {
                        preview = document.createElement('img');
                        preview.className = 'image-preview img-thumbnail mt-2';
                        preview.style.maxHeight = '200px';
                        input.parentNode.appendChild(preview);
                    }
                    preview.src = e.target.result;
                };
                reader.readAsDataURL(file);
            }
        });
    });

    // Character input enhancement
    var characterInput = document.querySelector('textarea[name="characters"]');
    if (characterInput) {
        characterInput.addEventListener('input', function() {
            // Auto-format characters with proper spacing
            var value = this.value;
            value = value.replace(/,\s*/g, ', '); // Ensure proper spacing after commas
            this.value = value;
        });
    }

    // Value input formatting
    var valueInputs = document.querySelectorAll('input[name="estimated_value"]');
    valueInputs.forEach(function(input) {
        input.addEventListener('blur', function() {
            var value = parseFloat(this.value);
            if (!isNaN(value)) {
                this.value = value.toFixed(2);
            }
        });
    });

    // Responsive table enhancement
    var tables = document.querySelectorAll('.table-responsive');
    tables.forEach(function(table) {
        if (table.scrollWidth > table.clientWidth) {
            table.classList.add('table-scrollable');
        }
    });

    // Lazy loading for images
    var images = document.querySelectorAll('img[data-src]');
    var imageObserver = new IntersectionObserver(function(entries, observer) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                var img = entry.target;
                img.src = img.dataset.src;
                img.classList.remove('lazy');
                imageObserver.unobserve(img);
            }
        });
    });

    images.forEach(function(img) {
        imageObserver.observe(img);
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + N for new comic
        if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
            e.preventDefault();
            var newComicLink = document.querySelector('a[href*="/comics/new"]');
            if (newComicLink) {
                window.location.href = newComicLink.href;
            }
        }
        
        // Ctrl/Cmd + S for search focus
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            var searchInput = document.querySelector('input[name="search"]');
            if (searchInput) {
                searchInput.focus();
            }
        }
    });

    // Export functionality enhancement
    var exportBtn = document.querySelector('a[href*="/comics/export"]');
    if (exportBtn) {
        exportBtn.addEventListener('click', function(e) {
            // Show loading state
            var originalText = this.innerHTML;
            this.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Exporting...';
            this.disabled = true;
            
            // Reset after a delay (in case of error)
            setTimeout(function() {
                exportBtn.innerHTML = originalText;
                exportBtn.disabled = false;
            }, 5000);
        });
    }

    // Dark mode toggle functionality
    var darkModeToggleDropdown = document.getElementById('darkModeToggleDropdown');
    var darkModeToggleNav = document.getElementById('darkModeToggleNav');
    
    // Initialize dark mode based on user preference or local storage
    function initializeDarkMode() {
        var isDark = false;
        
        // Check if user is authenticated and has a preference
        if (typeof currentUserDarkMode !== 'undefined') {
            isDark = currentUserDarkMode;
        } else {
            // Fall back to local storage
            var savedDarkMode = localStorage.getItem('darkMode');
            isDark = savedDarkMode === 'true';
        }
        
        if (isDark) {
            document.body.classList.add('dark-mode');
            if (darkModeToggleDropdown) darkModeToggleDropdown.checked = true;
            if (darkModeToggleNav) darkModeToggleNav.checked = true;
        } else {
            document.body.classList.remove('dark-mode');
            if (darkModeToggleDropdown) darkModeToggleDropdown.checked = false;
            if (darkModeToggleNav) darkModeToggleNav.checked = false;
        }
    }
    
    // Initialize on page load
    initializeDarkMode();
    
    // Function to handle dark mode toggle
    function handleDarkModeToggle(isDark) {
        // Update UI immediately
        if (isDark) {
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.remove('dark-mode');
        }
        
        // Sync both toggles
        if (darkModeToggleDropdown) darkModeToggleDropdown.checked = isDark;
        if (darkModeToggleNav) darkModeToggleNav.checked = isDark;
        
        // Save to local storage as fallback
        localStorage.setItem('darkMode', isDark);
        
        // Send preference to server if user is authenticated
        if (typeof currentUserAuthenticated !== 'undefined' && currentUserAuthenticated) {
            fetch('/api/dark-mode', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    dark_mode: isDark
                })
            })
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    console.error('Failed to save dark mode preference:', data.message);
                }
            })
            .catch(error => {
                console.error('Error saving dark mode preference:', error);
            });
        }
    }
    
    // Add event listeners to both toggles
    if (darkModeToggleDropdown) {
        darkModeToggleDropdown.addEventListener('change', function() {
            handleDarkModeToggle(this.checked);
        });
    }
    
    if (darkModeToggleNav) {
        darkModeToggleNav.addEventListener('change', function() {
            handleDarkModeToggle(this.checked);
        });
    }

    // Print functionality
    var printBtn = document.querySelector('.print-btn');
    if (printBtn) {
        printBtn.addEventListener('click', function() {
            window.print();
        });
    }

    // Confirmation dialogs enhancement
    var deleteButtons = document.querySelectorAll('[data-confirm]');
    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            var message = this.dataset.confirm || 'Are you sure?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });

    // Auto-save form data (optional enhancement)
    var forms = document.querySelectorAll('form[data-autosave]');
    forms.forEach(function(form) {
        var formId = form.dataset.autosave;
        var savedData = localStorage.getItem('form_' + formId);
        
        if (savedData) {
            try {
                var data = JSON.parse(savedData);
                Object.keys(data).forEach(function(key) {
                    var input = form.querySelector('[name="' + key + '"]');
                    if (input) {
                        input.value = data[key];
                    }
                });
            } catch (e) {
                console.error('Error loading saved form data:', e);
            }
        }
        
        // Save form data on input
        form.addEventListener('input', function() {
            var formData = {};
            var inputs = form.querySelectorAll('input, textarea, select');
            inputs.forEach(function(input) {
                if (input.name) {
                    formData[input.name] = input.value;
                }
            });
            localStorage.setItem('form_' + formId, JSON.stringify(formData));
        });
    });
});

// Utility functions
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

function debounce(func, wait) {
    var timeout;
    return function executedFunction() {
        var later = function() {
            clearTimeout(timeout);
            func();
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Export functions for global use
window.ComicBookManager = {
    formatCurrency: formatCurrency,
    debounce: debounce
};
