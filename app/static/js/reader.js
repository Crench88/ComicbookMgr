(function () {
    const shell = document.getElementById('readerShell');
    if (!shell) return;

    const img = document.getElementById('readerPageImage');
    const imgB = document.getElementById('readerPageImageB');
    const pageFrame = document.getElementById('readerPageFrame');
    const panelHits = document.getElementById('readerPanelHits');
    const panelFocus = document.getElementById('readerPanelFocus');
    const panelPop = document.getElementById('readerPanelPop');
    const panelCrop = document.getElementById('readerPanelCrop');
    const panelCaption = document.getElementById('readerPanelCaption');
    const panelFocusClose = document.getElementById('panelFocusClose');
    const pageInput = document.getElementById('readerPageInput');
    const slider = document.getElementById('readerSlider');
    const prevBtn = document.getElementById('readerPrev');
    const nextBtn = document.getElementById('readerNext');
    const hotPrev = document.getElementById('hotPrev');
    const hotNext = document.getElementById('hotNext');
    const fitWidthBtn = document.getElementById('fitWidth');
    const fitHeightBtn = document.getElementById('fitHeight');
    const spreadBtn = document.getElementById('spreadToggle');
    const panelModeBtn = document.getElementById('panelModeToggle');
    const hint = document.getElementById('readerHint');

    let page = parseInt(shell.dataset.page, 10) || 1;
    let spread = false;
    let panelMode = false;
    let panels = [];
    let panelIndex = -1;
    let panelFocusOpen = false;
    let panelFocusLockUntil = 0;
    let progressTimer = null;
    const pageCount = parseInt(shell.dataset.pageCount, 10) || 1;
    const pageUrlTemplate = shell.dataset.pageUrlTemplate || '';
    const panelsUrlTemplate = shell.dataset.panelsUrlTemplate || '';
    const progressUrl = shell.dataset.progressUrl || '';
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const prefetched = new Set();
    const PANEL_SCALE = 1.15;
    const panelsCache = new Map();

    function pageUrl(n) {
        return pageUrlTemplate.replace(/\/page\/\d+(?=\/?|$)/, '/page/' + n);
    }

    function panelsUrl(n) {
        // Support /page/0/panels regardless of how the template was generated.
        return panelsUrlTemplate.replace(/\/page\/\d+\/panels/, '/page/' + n + '/panels');
    }

    function step() {
        return spread ? 2 : 1;
    }

    function setFit(mode) {
        [img, imgB].forEach(function (el) {
            if (!el) return;
            el.classList.remove('fit-width', 'fit-height');
            el.classList.add(mode === 'height' ? 'fit-height' : 'fit-width');
        });
        fitWidthBtn.classList.toggle('active', mode !== 'height');
        fitHeightBtn.classList.toggle('active', mode === 'height');
        try {
            localStorage.setItem('readerFit', mode);
        } catch (e) { /* ignore */ }
        if (panelMode) {
            layoutPanelHits();
        }
        if (panelFocusOpen) {
            window.requestAnimationFrame(function () {
                showPanelFocus(panelIndex);
            });
        }
    }

    function prefetch(n) {
        if (n < 1 || n > pageCount || prefetched.has(n)) return;
        prefetched.add(n);
        const pre = new Image();
        pre.src = pageUrl(n);
    }

    function persist(n) {
        if (!progressUrl) return;
        if (progressTimer) clearTimeout(progressTimer);
        progressTimer = setTimeout(function () {
            fetch(progressUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrf,
                },
                body: JSON.stringify({ page: n }),
            }).catch(function () { /* ignore transient errors */ });
        }, 400);
    }

    function closePanelFocus() {
        panelFocusOpen = false;
        panelIndex = -1;
        if (panelFocus) panelFocus.hidden = true;
        if (panelCrop) {
            panelCrop.removeAttribute('src');
            panelCrop.removeAttribute('style');
        }
        if (panelPop) panelPop.removeAttribute('style');
        shell.classList.remove('panel-focus-active');
        updateHint();
    }

    function clearPanelHits() {
        if (!panelHits) return;
        panelHits.innerHTML = '';
        panelHits.hidden = true;
    }

    function panelContains(panel, nx, ny) {
        return nx >= panel.x && ny >= panel.y
            && nx <= panel.x + panel.w
            && ny <= panel.y + panel.h;
    }

    function findPanelAtClientPoint(clientX, clientY) {
        if (!img || !panels.length) return -1;
        const rect = img.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return -1;
        const nx = (clientX - rect.left) / rect.width;
        const ny = (clientY - rect.top) / rect.height;
        if (nx < 0 || ny < 0 || nx > 1 || ny > 1) return -1;

        // Prefer the smallest containing panel (nested/overlapping detections).
        let best = -1;
        let bestArea = Infinity;
        panels.forEach(function (panel, index) {
            if (!panelContains(panel, nx, ny)) return;
            const area = panel.w * panel.h;
            if (area < bestArea) {
                bestArea = area;
                best = index;
            }
        });
        return best;
    }

    function layoutPanelHits() {
        if (!panelMode || !panelHits || !img.complete || !img.naturalWidth) {
            clearPanelHits();
            return;
        }
        panelHits.hidden = false;
        panelHits.innerHTML = '';
        panels.forEach(function (panel, index) {
            const hit = document.createElement('button');
            hit.type = 'button';
            hit.className = 'reader-panel-hit';
            hit.style.left = (panel.x * 100) + '%';
            hit.style.top = (panel.y * 100) + '%';
            hit.style.width = (panel.w * 100) + '%';
            hit.style.height = (panel.h * 100) + '%';
            hit.setAttribute('aria-label', 'Zoom panel ' + (index + 1));
            hit.dataset.panelIndex = String(index);
            hit.addEventListener('pointerup', function (event) {
                // pointerup + preventDefault avoids the "open then immediate close"
                // ghost-click on the backdrop that plagues touch devices.
                event.preventDefault();
                event.stopPropagation();
                showPanelFocus(index);
            });
            hit.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
            });
            panelHits.appendChild(hit);
        });
    }

    function showPanelFocus(index) {
        if (!panels.length || !panelFocus || !panelCrop || !panelPop) return;
        index = Math.max(0, Math.min(panels.length - 1, index | 0));
        const panel = panels[index];
        if (!panel) return;

        panelIndex = index;
        panelFocusOpen = true;
        panelFocusLockUntil = Date.now() + 350;
        shell.classList.add('panel-focus-active');

        const stage = document.getElementById('readerStage');
        const stageRect = stage ? stage.getBoundingClientRect() : { width: window.innerWidth, height: window.innerHeight };
        const rect = img.getBoundingClientRect();
        const displayW = rect.width || img.clientWidth || img.naturalWidth || 1;
        const displayH = rect.height || img.clientHeight || img.naturalHeight || 1;

        const cropW = Math.max(32, panel.w * displayW);
        const cropH = Math.max(32, panel.h * displayH);

        // Fit the panel into the stage, then add the requested 15% pop.
        const maxW = Math.max(120, stageRect.width * 0.92);
        const maxH = Math.max(120, stageRect.height * 0.86);
        const fitScale = Math.min(maxW / cropW, maxH / cropH);
        // Always at least 1.15x the on-page size; usually larger to fill the viewport.
        const finalScale = Math.max(PANEL_SCALE, fitScale);
        const scaledW = cropW * finalScale;
        const scaledH = cropH * finalScale;

        panelCrop.src = img.currentSrc || img.src;
        panelCrop.style.width = (displayW * finalScale) + 'px';
        panelCrop.style.height = (displayH * finalScale) + 'px';
        panelCrop.style.maxWidth = 'none';
        panelCrop.style.marginLeft = (-panel.x * displayW * finalScale) + 'px';
        panelCrop.style.marginTop = (-panel.y * displayH * finalScale) + 'px';
        panelCrop.alt = 'Panel ' + (index + 1) + ' of ' + panels.length;

        panelPop.style.width = scaledW + 'px';
        panelPop.style.height = scaledH + 'px';
        panelPop.style.maxWidth = maxW + 'px';
        panelPop.style.maxHeight = maxH + 'px';
        panelFocus.hidden = false;

        panelPop.classList.remove('is-popping');
        void panelPop.offsetWidth;
        panelPop.classList.add('is-popping');

        if (panelCaption) {
            panelCaption.textContent = 'Panel ' + (index + 1) + ' / ' + panels.length;
        }
        updateHint();
    }

    function fetchPanels(n) {
        if (!panelsUrlTemplate) {
            return Promise.resolve([{ x: 0, y: 0, w: 1, h: 1 }]);
        }
        if (panelsCache.has(n)) {
            return Promise.resolve(panelsCache.get(n));
        }
        return fetch(panelsUrl(n), {
            headers: { Accept: 'application/json' },
            credentials: 'same-origin',
        })
            .then(function (resp) {
                if (!resp.ok) throw new Error('panels ' + resp.status);
                return resp.json();
            })
            .then(function (data) {
                const list = (data && data.panels && data.panels.length)
                    ? data.panels
                    : [{ x: 0, y: 0, w: 1, h: 1 }];
                panelsCache.set(n, list);
                return list;
            })
            .catch(function () {
                return [{ x: 0, y: 0, w: 1, h: 1 }];
            });
    }

    function activatePanelMode(enabled) {
        panelMode = !!enabled;
        if (panelModeBtn) panelModeBtn.classList.toggle('active', panelMode);
        shell.classList.toggle('panel-mode', panelMode);
        try {
            localStorage.setItem('readerPanelMode', panelMode ? '1' : '0');
        } catch (e) { /* ignore */ }

        if (!panelMode) {
            closePanelFocus();
            clearPanelHits();
            updateHint();
            return;
        }

        if (spread) {
            setSpread(false);
        }

        fetchPanels(page).then(function (list) {
            if (!panelMode) return;
            panels = list;
            layoutPanelHits();
            // Leave focus closed so the user can tap a panel; outlines show targets.
            closePanelFocus();
            updateHint();
        });
    }

    function updateHint() {
        if (!hint) return;
        if (panelFocusOpen) {
            hint.textContent = 'Panel zoomed 115% · ← → next panel · tap outside or Esc to close · P toggles panel mode';
        } else if (panelMode) {
            hint.textContent = 'Panel mode on · tap a highlighted panel to zoom 115% · ← → pages · P to exit';
        } else {
            hint.textContent = '← → or A/D to turn pages · P for panel zoom · S for spread · click edges · Esc to leave';
        }
    }

    function advancePanel(delta) {
        if (!panelMode || !panels.length) {
            goTo(page + (delta > 0 ? step() : -step()));
            return;
        }
        if (!panelFocusOpen) {
            showPanelFocus(delta > 0 ? 0 : panels.length - 1);
            return;
        }
        const nextIndex = panelIndex + delta;
        if (nextIndex >= 0 && nextIndex < panels.length) {
            showPanelFocus(nextIndex);
            return;
        }
        closePanelFocus();
        const nextPage = page + (delta > 0 ? step() : -step());
        if (nextPage < 1 || nextPage > pageCount) {
            if (panels.length) showPanelFocus(delta > 0 ? panels.length - 1 : 0);
            return;
        }
        goTo(nextPage, { openFirstPanel: delta > 0, openLastPanel: delta < 0 });
    }

    function render(options) {
        options = options || {};
        img.src = pageUrl(page);
        img.alt = 'Page ' + page + ' of ' + pageCount;

        const second = page + 1;
        if (spread && second <= pageCount) {
            imgB.src = pageUrl(second);
            imgB.alt = 'Page ' + second + ' of ' + pageCount;
            imgB.classList.remove('d-none');
        } else {
            imgB.classList.add('d-none');
            imgB.removeAttribute('src');
        }

        pageInput.value = String(page);
        slider.value = String(page);
        prevBtn.disabled = page <= 1;
        nextBtn.disabled = page + (spread ? 1 : 0) >= pageCount;

        for (let i = 1; i <= step() + 1; i += 1) {
            prefetch(page + step() + i - 1);
        }
        prefetch(page - 1);

        if (panelMode) {
            closePanelFocus();
            fetchPanels(page).then(function (list) {
                if (!panelMode) return;
                panels = list;
                layoutPanelHits();
                if (options.openFirstPanel && panels.length) {
                    showPanelFocus(0);
                } else if (options.openLastPanel && panels.length) {
                    showPanelFocus(panels.length - 1);
                }
            });
        } else {
            clearPanelHits();
        }
        updateHint();
    }

    function goTo(n, options) {
        const pushHistory = !options || options.pushHistory !== false;
        n = Math.max(1, Math.min(pageCount, n | 0));
        if (n === page && img.getAttribute('src')) {
            render(options);
            return;
        }
        page = n;
        shell.dataset.page = String(page);
        render(options);
        persist(n);
        if (pushHistory) {
            const url = new URL(window.location.href);
            url.searchParams.set('page', String(n));
            history.replaceState({ page: n }, '', url.toString());
        }
    }

    function setSpread(enabled) {
        spread = !!enabled;
        if (spread && panelMode) {
            activatePanelMode(false);
        }
        spreadBtn.classList.toggle('active', spread);
        shell.classList.toggle('spread-mode', spread);
        try {
            localStorage.setItem('readerSpread', spread ? '1' : '0');
        } catch (e) { /* ignore */ }
        render();
    }

    function onNavPrevious() {
        if (panelMode) {
            advancePanel(-1);
        } else {
            goTo(page - step());
        }
    }

    function onNavNext() {
        if (panelMode) {
            advancePanel(1);
        } else {
            goTo(page + step());
        }
    }

    prevBtn.addEventListener('click', onNavPrevious);
    nextBtn.addEventListener('click', onNavNext);
    hotPrev.addEventListener('click', onNavPrevious);
    hotNext.addEventListener('click', onNavNext);
    spreadBtn.addEventListener('click', function () { setSpread(!spread); });
    if (panelModeBtn) {
        panelModeBtn.addEventListener('click', function () {
            activatePanelMode(!panelMode);
        });
    }
    if (panelFocusClose) {
        panelFocusClose.addEventListener('click', function (event) {
            event.preventDefault();
            if (Date.now() < panelFocusLockUntil) return;
            closePanelFocus();
        });
        panelFocusClose.addEventListener('pointerup', function (event) {
            event.preventDefault();
            if (Date.now() < panelFocusLockUntil) return;
            closePanelFocus();
        });
    }

    // Coordinate click fallback: works even when overlay hit boxes miss.
    if (pageFrame) {
        pageFrame.addEventListener('pointerup', function (event) {
            if (!panelMode || panelFocusOpen) return;
            if (event.pointerType === 'mouse' && event.button !== 0) return;
            const index = findPanelAtClientPoint(event.clientX, event.clientY);
            if (index < 0) return;
            event.preventDefault();
            event.stopPropagation();
            showPanelFocus(index);
        });
    }

    pageInput.addEventListener('change', function () {
        goTo(parseInt(pageInput.value, 10) || page);
    });

    slider.addEventListener('input', function () {
        pageInput.value = slider.value;
    });
    slider.addEventListener('change', function () {
        goTo(parseInt(slider.value, 10) || page);
    });

    fitWidthBtn.addEventListener('click', function () { setFit('width'); });
    fitHeightBtn.addEventListener('click', function () { setFit('height'); });

    img.addEventListener('load', function () {
        if (panelMode) layoutPanelHits();
        if (panelFocusOpen) showPanelFocus(panelIndex);
    });

    window.addEventListener('resize', function () {
        if (panelMode) layoutPanelHits();
        if (panelFocusOpen) showPanelFocus(panelIndex);
    });

    document.addEventListener('keydown', function (event) {
        const tag = (event.target && event.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA') return;

        if (event.key === 'p' || event.key === 'P') {
            event.preventDefault();
            activatePanelMode(!panelMode);
            return;
        }

        if (event.key === 'Escape') {
            if (panelFocusOpen) {
                event.preventDefault();
                closePanelFocus();
                return;
            }
            if (panelMode) {
                event.preventDefault();
                activatePanelMode(false);
                return;
            }
            const back = document.querySelector('.reader-back');
            if (back) window.location.href = back.href;
            return;
        }

        if (event.key === 'ArrowRight' || event.key === 'd' || event.key === 'D' || event.key === ' ') {
            event.preventDefault();
            onNavNext();
        } else if (event.key === 'ArrowLeft' || event.key === 'a' || event.key === 'A') {
            event.preventDefault();
            onNavPrevious();
        } else if (event.key === 's' || event.key === 'S') {
            event.preventDefault();
            setSpread(!spread);
        } else if (event.key === 'Home') {
            event.preventDefault();
            goTo(1);
        } else if (event.key === 'End') {
            event.preventDefault();
            goTo(pageCount);
        }
    });

    let storedFit = 'width';
    let storedSpread = '0';
    let storedPanel = '0';
    try {
        storedFit = localStorage.getItem('readerFit') || 'width';
        storedSpread = localStorage.getItem('readerSpread') || '0';
        storedPanel = localStorage.getItem('readerPanelMode') || '0';
    } catch (e) { /* ignore */ }
    setFit(storedFit === 'height' ? 'height' : 'width');
    spread = storedSpread === '1';
    spreadBtn.classList.toggle('active', spread);
    shell.classList.toggle('spread-mode', spread);
    render();
    if (storedPanel === '1') {
        activatePanelMode(true);
    } else {
        updateHint();
    }
})();
