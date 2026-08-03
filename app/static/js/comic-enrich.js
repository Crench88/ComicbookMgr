/**
 * Shared comic enrichment: ComicVine metadata, cover barcode scan, and eBay value.
 * Used by the show page and the add/edit comic form.
 */
(function (global) {
    'use strict';

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    function csrfHeaders(extra) {
        var headers = Object.assign({ 'Content-Type': 'application/json' }, extra || {});
        var token = csrfToken();
        if (token) {
            headers['X-CSRFToken'] = token;
        }
        return headers;
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    var currencyFormatters = {};

    function formatMoney(amount, currency) {
        var code = currency || 'CAD';
        if (!currencyFormatters[code]) {
            try {
                currencyFormatters[code] = new Intl.NumberFormat('en-CA', {
                    style: 'currency',
                    currency: code,
                });
            } catch (error) {
                currencyFormatters[code] = {
                    format: function (value) {
                        return code + ' ' + Number(value).toFixed(2);
                    },
                };
            }
        }
        return currencyFormatters[code].format(amount);
    }

    function normalizeEstimate(data) {
        if (data && data.estimate) {
            return data.estimate;
        }
        var value = data && data.estimated_value;
        return {
            value: value,
            low: value,
            high: value,
            currency: 'CAD',
            source: 'estimate',
            source_label: 'Offline estimate',
            confidence: 'low',
            confidence_note: '',
            basis: '',
            notes: [],
            comps: [],
        };
    }

    function fieldsFromMetadata(metadata, fallback) {
        var meta = metadata || {};
        var base = fallback || {};
        return {
            series: meta.series || base.series || '',
            title: meta.title || base.title || '',
            issue_number: meta.issue_number || base.issue_number || '',
            publisher: meta.publisher || base.publisher || '',
            condition: base.condition || '',
        };
    }

    /**
     * Refresh ComicVine metadata for a saved comic.
     * @param {string|number} comicId
     * @param {{ method?: 'GET'|'POST', naPublishersOnly?: boolean }} [options]
     */
    async function refreshComicVine(comicId, options) {
        options = options || {};
        if (!comicId) {
            return { ok: false, skipped: true, error: 'Comic must be saved before ComicVine refresh.' };
        }
        var method = (options.method || 'GET').toUpperCase();
        var params = new URLSearchParams();
        if (options.naPublishersOnly === true) {
            params.set('na_publishers_only', '1');
        } else if (options.naPublishersOnly === false) {
            params.set('na_publishers_only', '0');
        }
        var query = params.toString();
        var url = '/comics/' + comicId + '/comicvine/refresh' + (query ? '?' + query : '');
        var response = await fetch(url, {
            method: method,
            headers: method === 'POST' ? csrfHeaders() : undefined,
            body: method === 'POST' ? JSON.stringify({}) : undefined,
        });
        var data = await response.json();
        if (!response.ok || data.error) {
            return {
                ok: false,
                status: response.status,
                error: data.error || 'ComicVine refresh failed.',
                data: data,
            };
        }
        return { ok: true, status: response.status, data: data };
    }

    /**
     * Scan cover images for a UPC barcode.
     * @param {string|number} comicId
     * @param {{ overwrite?: boolean, confirmOverwrite?: function }} [options]
     */
    async function scanBarcode(comicId, options) {
        options = options || {};
        if (!comicId) {
            return { ok: false, skipped: true, error: 'Comic must be saved (with a cover) before barcode scan.' };
        }

        async function attempt(overwrite) {
            var response = await fetch('/comics/' + comicId + '/scan-barcode', {
                method: 'POST',
                headers: csrfHeaders(),
                body: JSON.stringify({ overwrite: !!overwrite }),
            });
            var data = await response.json();
            if (response.status === 409 && data.needs_confirmation) {
                var confirmFn = options.confirmOverwrite || function (payload) {
                    return window.confirm(
                        'Found barcode ' + payload.upc + ', but this comic already has UPC ' +
                        payload.existing_upc + '. Replace it?'
                    );
                };
                if (confirmFn(data)) {
                    return attempt(true);
                }
                return {
                    ok: false,
                    cancelled: true,
                    status: 409,
                    error: 'Scan cancelled — existing UPC kept.',
                    data: data,
                };
            }
            if (!response.ok || !data.success) {
                return {
                    ok: false,
                    status: response.status,
                    error: data.error || 'No barcode found.',
                    data: data,
                };
            }
            return { ok: true, status: response.status, data: data };
        }

        return attempt(!!options.overwrite);
    }

    /**
     * Look up eBay Canada market value from comic identity fields.
     * @param {{ series?: string, title?: string, issue_number?: string, publisher?: string, condition?: string }} fields
     */
    async function lookupValue(fields) {
        fields = fields || {};
        var series = (fields.series || '').trim();
        var title = (fields.title || '').trim();
        var issueNumber = (fields.issue_number || '').trim();
        if (!series && !title && !issueNumber) {
            return {
                ok: false,
                skipped: true,
                error: 'Series, title, or issue number is required for value lookup.',
            };
        }

        var response = await fetch('/comics/ai-value-lookup', {
            method: 'POST',
            headers: csrfHeaders(),
            body: JSON.stringify({
                series: series,
                title: title,
                issue_number: issueNumber,
                publisher: (fields.publisher || '').trim(),
                condition: (fields.condition || '').trim(),
            }),
        });
        var data = await response.json();
        if (!response.ok || !data.success) {
            return {
                ok: false,
                status: response.status,
                error: (data && data.error) || 'Failed to estimate a value.',
                data: data,
            };
        }
        return {
            ok: true,
            status: response.status,
            data: data,
            estimate: normalizeEstimate(data),
        };
    }

    /**
     * Persist an estimated value on a saved comic.
     */
    async function saveEstimatedValue(comicId, value) {
        if (!comicId) {
            return { ok: false, skipped: true, error: 'Comic must be saved before updating estimated value.' };
        }
        var response = await fetch('/comics/' + comicId + '/estimated-value', {
            method: 'POST',
            headers: csrfHeaders(),
            body: JSON.stringify({ estimated_value: value }),
        });
        var data = await response.json();
        if (!response.ok || !data.success) {
            return {
                ok: false,
                status: response.status,
                error: (data && data.error) || 'Could not save estimated value.',
                data: data,
            };
        }
        return { ok: true, status: response.status, data: data };
    }

    function renderCompsHtml(estimate) {
        if (!estimate.comps || !estimate.comps.length) {
            return '';
        }
        var rows = estimate.comps.map(function (comp) {
            var grade = comp.assumed_grade
                ? 'grade not stated'
                : 'graded ' + escapeHtml(String(comp.source_grade));
            var listed = formatMoney(comp.total, comp.currency || estimate.currency);
            var adjusted = formatMoney(comp.adjusted, estimate.currency);
            var link = comp.url
                ? '<a href="' + escapeHtml(comp.url) + '" target="_blank" rel="noopener noreferrer">' +
                  escapeHtml(comp.title) + '</a>'
                : escapeHtml(comp.title);
            return '<li class="small">' + link + '<br><span class="text-muted">' +
                escapeHtml(listed) + ' listed, ' + grade + ' &rarr; ' + escapeHtml(adjusted) +
                ' at your condition</span></li>';
        }).join('');
        return (
            '<details class="mt-2">' +
            '<summary class="small">Comparable listings used (' + estimate.comps.length + ')</summary>' +
            '<ul class="mt-2 mb-0 ps-3">' + rows + '</ul></details>'
        );
    }

    /**
     * Render a value estimate panel into a host element.
     * @param {HTMLElement} host
     * @param {object} estimate
     * @param {{ onApply?: function, applyLabel?: string, panelId?: string }} [options]
     */
    function renderValuePanel(host, estimate, options) {
        options = options || {};
        if (!host || !estimate) {
            return null;
        }
        host.innerHTML = '';
        var fromMarket = estimate.source === 'ebay';
        var panel = document.createElement('div');
        panel.id = options.panelId || 'valueEstimatePanel';
        panel.className = 'alert ' + (fromMarket ? 'alert-success' : 'alert-secondary') + ' mb-0 py-2';

        var headline =
            formatMoney(estimate.value, estimate.currency) +
            ' <span class="text-muted small">(' +
            escapeHtml(formatMoney(estimate.low, estimate.currency)) +
            ' &ndash; ' +
            escapeHtml(formatMoney(estimate.high, estimate.currency)) +
            ')</span>';
        var notes = (estimate.notes || []).map(function (note) {
            return '<div class="small text-muted">' + escapeHtml(note) + '</div>';
        }).join('');
        var searchLink = estimate.search_url
            ? '<a class="small" href="' + escapeHtml(estimate.search_url) +
              '" target="_blank" rel="noopener noreferrer">See all listings</a>'
            : '';
        var applyHtml = '';
        if (typeof options.onApply === 'function') {
            applyHtml =
                '<button type="button" class="btn btn-sm btn-success" data-enrich-apply-value>' +
                escapeHtml(options.applyLabel || ('Save ' + formatMoney(estimate.value, estimate.currency) + ' as estimated value')) +
                '</button>';
        }

        panel.innerHTML =
            '<button type="button" class="btn-close float-end" aria-label="Dismiss value estimate"></button>' +
            '<div><i class="bi ' + (fromMarket ? 'bi-graph-up' : 'bi-info-circle') + '"></i> <strong>' +
            headline + '</strong></div>' +
            '<div class="small">' + escapeHtml(estimate.source_label) + ' &middot; ' +
            escapeHtml(estimate.confidence) + ' confidence &middot; ' +
            escapeHtml(estimate.confidence_note) + '</div>' +
            '<div class="small text-muted">' + escapeHtml(estimate.basis) + '</div>' +
            notes +
            renderCompsHtml(estimate) +
            '<div class="mt-2 d-flex flex-wrap gap-2 align-items-center">' + applyHtml + searchLink + '</div>';

        panel.querySelector('.btn-close').addEventListener('click', function () {
            host.innerHTML = '';
        });
        var applyBtn = panel.querySelector('[data-enrich-apply-value]');
        if (applyBtn && typeof options.onApply === 'function') {
            applyBtn.addEventListener('click', function () {
                options.onApply(estimate, applyBtn);
            });
        }
        host.appendChild(panel);
        return panel;
    }

    /**
     * One-click enrich: ComicVine + barcode + eBay value (each step optional / skippable).
     *
     * @param {{
     *   comicId?: string|number,
     *   fields?: object,
     *   comicvineMethod?: 'GET'|'POST',
     *   naPublishersOnly?: boolean,
     *   refreshComicVine?: boolean,
     *   scanBarcode?: boolean,
     *   lookupValue?: boolean,
     *   saveValue?: boolean,
     *   confirm?: boolean|string,
     *   getFields?: function,
     *   onStatus?: function,
     *   onComicVine?: function,
     *   onBarcode?: function,
     *   onValue?: function,
     * }} options
     */
    async function enrichAll(options) {
        options = options || {};
        var comicId = options.comicId || null;
        var doComicVine = options.refreshComicVine !== false && !!comicId;
        var doBarcode = options.scanBarcode !== false && !!comicId;
        var doValue = options.lookupValue !== false;
        var saveValue = !!options.saveValue && !!comicId;
        var onStatus = typeof options.onStatus === 'function' ? options.onStatus : function () {};

        if (options.confirm !== false) {
            var message = typeof options.confirm === 'string'
                ? options.confirm
                : 'Enrich this comic from ComicVine, scan the cover barcode, and look up eBay market value?';
            if (!window.confirm(message)) {
                return { cancelled: true };
            }
        }

        var result = {
            cancelled: false,
            comicvine: null,
            barcode: null,
            value: null,
            savedValue: null,
        };

        var fields = Object.assign({}, options.fields || {});
        if (typeof options.getFields === 'function') {
            fields = Object.assign(fields, options.getFields() || {});
        }

        if (doComicVine) {
            onStatus('Refreshing metadata from ComicVine…', 'info');
            result.comicvine = await refreshComicVine(comicId, {
                method: options.comicvineMethod || 'GET',
                naPublishersOnly: options.naPublishersOnly,
            });
            if (typeof options.onComicVine === 'function') {
                await options.onComicVine(result.comicvine);
            }
            if (result.comicvine.ok && result.comicvine.data && result.comicvine.data.metadata) {
                fields = fieldsFromMetadata(result.comicvine.data.metadata, fields);
            }
            if (typeof options.getFields === 'function') {
                // Prefer live form values after ComicVine fill handlers run.
                fields = Object.assign(fields, options.getFields() || {});
            }
        } else if (options.refreshComicVine !== false && !comicId) {
            result.comicvine = {
                ok: false,
                skipped: true,
                error: 'Save the comic first to refresh ComicVine metadata.',
            };
        }

        var parallel = [];
        if (doBarcode) {
            onStatus('Scanning cover for barcode…', 'info');
            parallel.push(
                scanBarcode(comicId).then(function (barcodeResult) {
                    result.barcode = barcodeResult;
                    if (typeof options.onBarcode === 'function') {
                        return options.onBarcode(barcodeResult);
                    }
                })
            );
        } else if (options.scanBarcode !== false && !comicId) {
            result.barcode = {
                ok: false,
                skipped: true,
                error: 'Save the comic with a cover first to scan a barcode.',
            };
        }

        if (doValue) {
            onStatus('Looking up eBay market value…', 'info');
            parallel.push(
                lookupValue(fields).then(function (valueResult) {
                    result.value = valueResult;
                    if (typeof options.onValue === 'function') {
                        return options.onValue(valueResult);
                    }
                })
            );
        }

        if (parallel.length) {
            await Promise.all(parallel);
        }

        if (saveValue && result.value && result.value.ok && result.value.estimate) {
            onStatus('Saving estimated value…', 'info');
            result.savedValue = await saveEstimatedValue(comicId, result.value.estimate.value);
        }

        var parts = [];
        if (result.comicvine) {
            if (result.comicvine.ok) {
                parts.push('ComicVine updated');
            } else if (result.comicvine.skipped) {
                parts.push('ComicVine skipped');
            } else {
                parts.push('ComicVine failed');
            }
        }
        if (result.barcode) {
            if (result.barcode.ok) {
                parts.push('UPC ' + (result.barcode.data && result.barcode.data.upc));
            } else if (result.barcode.cancelled) {
                parts.push('barcode kept existing');
            } else if (result.barcode.skipped) {
                parts.push('barcode skipped');
            } else {
                parts.push('barcode not found');
            }
        }
        if (result.value) {
            if (result.value.ok) {
                parts.push('value ' + formatMoney(result.value.estimate.value, result.value.estimate.currency));
            } else if (result.value.skipped) {
                parts.push('value skipped');
            } else {
                parts.push('value lookup failed');
            }
        }
        if (result.savedValue && result.savedValue.ok) {
            parts.push('value saved');
        }

        var anyHardFailure =
            (result.comicvine && !result.comicvine.ok && !result.comicvine.skipped) ||
            (result.value && !result.value.ok && !result.value.skipped && doValue && !comicId);
        var level = anyHardFailure ? 'warning' : 'success';
        if (!parts.length) {
            onStatus('Nothing to enrich.', 'secondary');
        } else {
            onStatus(parts.join(' · '), level);
        }

        result.summary = parts.join(' · ');
        result.ok = !anyHardFailure;
        return result;
    }

    global.ComicEnrich = {
        csrfHeaders: csrfHeaders,
        escapeHtml: escapeHtml,
        formatMoney: formatMoney,
        refreshComicVine: refreshComicVine,
        scanBarcode: scanBarcode,
        lookupValue: lookupValue,
        saveEstimatedValue: saveEstimatedValue,
        renderValuePanel: renderValuePanel,
        enrichAll: enrichAll,
        fieldsFromMetadata: fieldsFromMetadata,
    };
})(window);
