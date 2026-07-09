// Comic Book Collection Manager — JavaScript

(function() {
    'use strict';

    var THEME_KEY = 'themePreference';
    var VALID_THEMES = ['light', 'dark', 'system'];

    function getStoredTheme() {
        try {
            var stored = localStorage.getItem(THEME_KEY);
            if (stored && VALID_THEMES.indexOf(stored) !== -1) {
                return stored;
            }
        } catch (e) {}
        return null;
    }

    function resolveTheme(preference) {
        if (preference === 'system') {
            return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        return preference;
    }

    function applyTheme(preference) {
        var resolved = resolveTheme(preference);
        document.documentElement.setAttribute('data-theme', resolved);
        document.documentElement.setAttribute('data-theme-pref', preference);

        document.querySelectorAll('.theme-switcher-btn').forEach(function(btn) {
            btn.classList.toggle('active', btn.dataset.theme === preference);
        });
    }

    function saveThemePreference(preference) {
        try {
            localStorage.setItem(THEME_KEY, preference);
        } catch (e) {}

        if (typeof currentUserAuthenticated !== 'undefined' && currentUserAuthenticated) {
            fetch('/api/theme', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ theme: preference })
            }).catch(function(err) {
                console.error('Failed to save theme preference:', err);
            });
        }
    }

    function initTheme() {
        var preference = getStoredTheme();
        if (!preference) {
            preference = (typeof userThemePreference !== 'undefined' && userThemePreference)
                ? userThemePreference
                : 'system';
        }
        applyTheme(preference);

        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function() {
            var current = document.documentElement.getAttribute('data-theme-pref') || 'system';
            if (current === 'system') {
                applyTheme('system');
            }
        });
    }

    function initThemeSwitchers() {
        document.querySelectorAll('.theme-switcher-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var theme = btn.dataset.theme;
                if (VALID_THEMES.indexOf(theme) === -1) return;
                applyTheme(theme);
                saveThemePreference(theme);
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        initTheme();
        initThemeSwitchers();

        // Tooltips
        var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function(el) { return new bootstrap.Tooltip(el); });

        // Popovers
        var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverTriggerList.map(function(el) { return new bootstrap.Popover(el); });

        // Auto-hide alerts
        setTimeout(function() {
            document.querySelectorAll('.alert').forEach(function(alert) {
                var bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                bsAlert.close();
            });
        }, 5000);

        // Form validation
        document.querySelectorAll('.needs-validation').forEach(function(form) {
            form.addEventListener('submit', function(event) {
                if (!form.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                }
                form.classList.add('was-validated');
            });
        });

        // Search debounce
        var searchInput = document.getElementById('search');
        if (searchInput && searchInput.form) {
            searchInput.addEventListener('input', function() {
                clearTimeout(searchInput.searchTimeout);
                searchInput.searchTimeout = setTimeout(function() {
                    if (searchInput.value.length >= 3 || searchInput.value.length === 0) {
                        searchInput.form.submit();
                    }
                }, 500);
            });
        }

        // Image preview for file uploads
        document.querySelectorAll('input[type="file"]').forEach(function(input) {
            input.addEventListener('change', function() {
                var file = this.files[0];
                if (!file) return;
                var reader = new FileReader();
                reader.onload = function(e) {
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
            });
        });

        // Character input formatting
        var characterInput = document.querySelector('textarea[name="characters"]');
        if (characterInput) {
            characterInput.addEventListener('input', function() {
                this.value = this.value.replace(/,\s*/g, ', ');
            });
        }

        // Value input formatting
        document.querySelectorAll('input[name="estimated_value"]').forEach(function(input) {
            input.addEventListener('blur', function() {
                var value = parseFloat(this.value);
                if (!isNaN(value)) {
                    this.value = value.toFixed(2);
                }
            });
        });

        // Export loading state
        var exportBtn = document.querySelector('a[href*="/comics/export"]');
        if (exportBtn) {
            exportBtn.addEventListener('click', function() {
                var originalText = this.innerHTML;
                this.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Exporting...';
                setTimeout(function() {
                    exportBtn.innerHTML = originalText;
                }, 5000);
            });
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
                e.preventDefault();
                var link = document.querySelector('a[href*="/comics/new"]');
                if (link) window.location.href = link.href;
            }
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                var search = document.querySelector('input[name="search"]');
                if (search) search.focus();
            }
        });

        // Confirmation dialogs
        document.querySelectorAll('[data-confirm]').forEach(function(button) {
            button.addEventListener('click', function(e) {
                if (!confirm(button.dataset.confirm || 'Are you sure?')) {
                    e.preventDefault();
                }
            });
        });

        initCollectionBrowser();
        initDeleteModal();
    });

    function initDeleteModal() {
        var deleteModalEl = document.getElementById('deleteModal');
        if (!deleteModalEl) return;

        window.confirmDelete = function(comicId, comicTitle) {
            var titleEl = document.getElementById('comicTitle');
            var form = document.getElementById('deleteForm');
            if (!titleEl || !form) return;

            titleEl.textContent = comicTitle || 'this comic';
            form.action = '/comics/' + comicId + '/delete';

            var nextInput = form.querySelector('input[name="next"]');
            if (nextInput) {
                nextInput.value = window.location.pathname + window.location.search;
            }

            bootstrap.Modal.getOrCreateInstance(deleteModalEl).show();
        };

        document.addEventListener('click', function(e) {
            var btn = e.target.closest('.delete-comic-btn');
            if (!btn) return;
            e.preventDefault();
            e.stopPropagation();
            window.confirmDelete(btn.dataset.comicId, btn.dataset.comicTitle || '');
        });
    }

    function initCollectionBrowser() {
        var browser = document.getElementById('collectionBrowser');
        if (!browser) return;

        function syncCollectionLayout() {
            var stickyBar = document.querySelector('.collection-sticky-bar');
            var navHeight = parseInt(
                getComputedStyle(document.documentElement).getPropertyValue('--nav-height'),
                10
            ) || 64;
            var stickyBarHeight = stickyBar ? stickyBar.offsetHeight : 0;
            var top = navHeight + stickyBarHeight + 12;
            document.documentElement.style.setProperty('--collection-sidebar-top', top + 'px');
        }

        syncCollectionLayout();
        window.addEventListener('resize', syncCollectionLayout);

        function escapeHtml(value) {
            return String(value)
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
        }

        var preview = document.getElementById('coverPreview');
        var grid = document.getElementById('coverGrid');
        var filterForm = document.getElementById('collectionFilterForm');
        var seriesIssuesUrl = browser.dataset.seriesIssuesUrl;

        function getFilterParams() {
            var params = new URLSearchParams();
            if (!filterForm) return params;
            filterForm.querySelectorAll('input, select').forEach(function(el) {
                if (el.type === 'checkbox') {
                    if (el.checked) params.set(el.name, el.value);
                } else if (el.name && el.value) {
                    params.set(el.name, el.value);
                }
            });
            return params;
        }

        function positionPreview(card, event) {
            if (!preview) return;
            var rect = card.getBoundingClientRect();
            var pw = preview.offsetWidth || 220;
            var ph = preview.offsetHeight || 320;
            var x = rect.right + 12;
            var y = rect.top;

            if (x + pw > window.innerWidth - 12) {
                x = rect.left - pw - 12;
            }
            if (y + ph > window.innerHeight - 12) {
                y = window.innerHeight - ph - 12;
            }
            if (y < 12) y = 12;
            if (x < 12) x = 12;

            preview.style.left = x + 'px';
            preview.style.top = y + 'px';
        }

        function showPreview(card, event) {
            if (!preview) return;
            var issue = card.dataset.issue || '';
            var title = card.dataset.title || '';
            var publisher = card.dataset.publisher || '';
            var condition = card.dataset.condition || '';
            var value = card.dataset.value || '';
            var wishlist = card.dataset.wishlist === 'true';
            var coverUrl = card.dataset.coverUrl || '';

            preview.querySelector('.cover-preview-issue').textContent = issue ? ('#' + issue) : 'Issue unknown';
            preview.querySelector('.cover-preview-title').textContent = title || '';
            var metaParts = [publisher];
            if (condition) metaParts.push(condition);
            if (value) metaParts.push(value);
            if (wishlist) metaParts.push('Wishlist');
            preview.querySelector('.cover-preview-meta').textContent = metaParts.filter(Boolean).join(' · ');

            var img = preview.querySelector('.cover-preview-image img');
            if (coverUrl) {
                img.src = coverUrl;
                img.alt = (issue ? ('#' + issue + ' ') : '') + title;
                img.style.display = '';
            } else {
                img.removeAttribute('src');
                img.alt = '';
                img.style.display = 'none';
            }

            preview.hidden = false;
            preview.setAttribute('aria-hidden', 'false');
            preview.classList.add('is-visible');
            positionPreview(card, event);
        }

        function hidePreview() {
            if (!preview) return;
            preview.classList.remove('is-visible');
            preview.hidden = true;
            preview.setAttribute('aria-hidden', 'true');
        }

        function bindCoverPreviews(container) {
            if (!container) return;
            container.querySelectorAll('.cover-card').forEach(function(card) {
                card.addEventListener('mouseenter', function(e) { showPreview(card, e); });
                card.addEventListener('mousemove', function(e) { positionPreview(card, e); });
                card.addEventListener('mouseleave', hidePreview);
                card.addEventListener('focusin', function(e) { showPreview(card, e); });
                card.addEventListener('focusout', hidePreview);
            });
        }

        function renderComicGrid(comics) {
            if (!grid) return;
            grid.innerHTML = '';
            if (!comics.length) {
                grid.innerHTML = '<p class="text-muted small mb-0">No issues match the current filters.</p>';
                return;
            }
            comics.forEach(function(comic) {
                var currentCollectionUrl = window.location.pathname + window.location.search;
                function withCollectionReturnUrl(url) {
                    var target = new URL(url, window.location.origin);
                    target.searchParams.set('next', currentCollectionUrl);
                    return target.pathname + target.search;
                }
                var showUrl = withCollectionReturnUrl(comic.show_url);
                var editUrl = withCollectionReturnUrl(comic.edit_url);
                var article = document.createElement('article');
                article.className = 'cover-card';
                article.dataset.comicId = comic.id;
                article.dataset.title = comic.title || '';
                article.dataset.issue = comic.issue_number || '';
                article.dataset.publisher = comic.publisher || 'Unknown';
                article.dataset.condition = comic.condition || '';
                article.dataset.value = comic.estimated_value || '';
                article.dataset.wishlist = comic.is_wishlist ? 'true' : 'false';
                article.dataset.coverUrl = comic.has_cover ? comic.cover_url : '';

                var badges = '';
                if (comic.is_wishlist) badges += '<span class="cover-card-badge wishlist">Wishlist</span>';
                if (comic.duplicate_total > 1) {
                    badges += '<span class="cover-card-badge duplicate">Copy ' + comic.duplicate_index + '/' + comic.duplicate_total + '</span>';
                }

                var imageHtml = comic.has_cover
                    ? '<img src="' + comic.cover_url + '" alt="#' + (comic.issue_number || '') + '" loading="lazy">'
                    : '<div class="cover-card-placeholder"><i class="bi bi-image"></i></div>';

                article.innerHTML =
                    '<a href="' + showUrl + '" class="cover-card-link">' +
                        '<div class="cover-card-image">' + imageHtml + badges + '</div>' +
                        '<div class="cover-card-caption">' +
                            '<span class="cover-card-issue">#' + (comic.issue_number || '?') + '</span>' +
                            (comic.title ? '<span class="cover-card-title">' + comic.title + '</span>' : '') +
                        '</div>' +
                    '</a>' +
                    '<div class="cover-card-actions">' +
                        '<a href="' + showUrl + '" class="btn btn-sm btn-outline-primary" title="View"><i class="bi bi-eye"></i></a>' +
                        '<a href="' + editUrl + '" class="btn btn-sm btn-outline-secondary" title="Edit"><i class="bi bi-pencil"></i></a>' +
                        '<button type="button" class="btn btn-sm btn-outline-danger delete-comic-btn" ' +
                            'data-comic-id="' + comic.id + '" ' +
                            'data-comic-title="' + escapeHtml(comic.title || '') + '" ' +
                            'title="Delete"><i class="bi bi-trash"></i></button>' +
                    '</div>';

                grid.appendChild(article);
            });
            bindCoverPreviews(grid);
        }

        function updatePaginationNav(pagination, seriesName) {
            var nav = document.getElementById('comicPagination');
            if (!nav || !pagination || pagination.pages <= 1) {
                if (nav) nav.innerHTML = '';
                return;
            }

            var params = getFilterParams();
            params.set('series', seriesName);
            var seriesPage = new URLSearchParams(window.location.search).get('series_page') || '1';
            params.set('series_page', seriesPage);

            function pageHref(page) {
                var p = new URLSearchParams(params.toString());
                p.set('comic_page', String(page));
                return window.location.pathname + '?' + p.toString();
            }

            var html = '<ul class="pagination pagination-sm mb-0 justify-content-center">';
            html += '<li class="page-item' + (pagination.has_prev ? '' : ' disabled') + '">';
            html += '<a class="page-link comic-page-link" data-page="' + (pagination.prev_num || 1) + '" href="' + pageHref(pagination.prev_num || 1) + '"><i class="bi bi-chevron-left"></i></a></li>';
            for (var i = 1; i <= pagination.pages; i++) {
                html += '<li class="page-item' + (i === pagination.page ? ' active' : '') + '">';
                html += '<a class="page-link comic-page-link" data-page="' + i + '" href="' + pageHref(i) + '">' + i + '</a></li>';
            }
            html += '<li class="page-item' + (pagination.has_next ? '' : ' disabled') + '">';
            html += '<a class="page-link comic-page-link" data-page="' + (pagination.next_num || pagination.pages) + '" href="' + pageHref(pagination.next_num || pagination.pages) + '"><i class="bi bi-chevron-right"></i></a></li>';
            html += '</ul>';
            nav.innerHTML = html;
            bindComicPagination(nav, seriesName);
        }

        function loadSeriesIssues(seriesName, comicPage, pushState) {
            var params = getFilterParams();
            params.set('series', seriesName);
            params.set('comic_page', String(comicPage || 1));

            return fetch(seriesIssuesUrl + '?' + params.toString(), {
                headers: { 'Accept': 'application/json' }
            })
            .then(function(resp) { return resp.json(); })
            .then(function(data) {
                renderComicGrid(data.comics || []);
                updatePaginationNav(data.pagination, seriesName);

                var titleEl = document.getElementById('seriesDetailTitle');
                var metaEl = document.getElementById('seriesDetailMeta');
                if (titleEl) titleEl.textContent = data.series;
                if (metaEl) {
                    var total = data.pagination ? data.pagination.total : 0;
                    var meta = total + ' issue' + (total === 1 ? '' : 's');
                    if (data.pagination && data.pagination.pages > 1) {
                        meta += ' · page ' + data.pagination.page + ' of ' + data.pagination.pages;
                    }
                    metaEl.textContent = meta;
                }

                browser.querySelectorAll('.series-list-item').forEach(function(link) {
                    var active = link.dataset.series === seriesName;
                    link.classList.toggle('is-active', active);
                    link.setAttribute('aria-selected', active ? 'true' : 'false');
                });

                if (pushState) {
                    params.set('series_page', new URLSearchParams(window.location.search).get('series_page') || '1');
                    history.pushState({ series: seriesName, comicPage: comicPage }, '', window.location.pathname + '?' + params.toString());
                }
            })
            .catch(function() {
                window.location.href = window.location.pathname + '?' + params.toString();
            });
        }

        function bindComicPagination(container, seriesName) {
            if (!container) return;
            container.querySelectorAll('.comic-page-link').forEach(function(link) {
                link.addEventListener('click', function(e) {
                    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
                    e.preventDefault();
                    loadSeriesIssues(seriesName, parseInt(link.dataset.page, 10) || 1, true);
                });
            });
        }

        browser.querySelectorAll('.series-list-item').forEach(function(link) {
            link.addEventListener('click', function(e) {
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
                e.preventDefault();
                loadSeriesIssues(link.dataset.series, 1, true);
            });
        });

        bindCoverPreviews(grid);
        var activeSeriesLink = browser.querySelector('.series-list-item.is-active');
        bindComicPagination(
            document.getElementById('comicPagination'),
            activeSeriesLink ? activeSeriesLink.dataset.series : ''
        );

        window.addEventListener('popstate', function() {
            var params = new URLSearchParams(window.location.search);
            var series = params.get('series');
            var comicPage = parseInt(params.get('comic_page') || '1', 10);
            if (series) loadSeriesIssues(series, comicPage, false);
        });
    }

    // Public API
    window.ComicBookManager = {
        setTheme: function(theme) {
            applyTheme(theme);
            saveThemePreference(theme);
        },
        getTheme: function() {
            return document.documentElement.getAttribute('data-theme-pref') || 'system';
        }
    };
})();
