// Layout only: never reads or changes orders, selections, or the dispatch ledger.
(() => {
    const host = window.parent, doc = host.document;
    let responseSignature = host.__sweaterDeskLayout?.responseSignature;
    let pageNoticeSignature = host.__sweaterDeskLayout?.pageNoticeSignature;
    host.__sweaterDeskLayout?.dispose();
    let ratio = .38, frame = 0, disposed = false;
    try { ratio = Number(host.sessionStorage.getItem('sweater-desk-order-width')) || .38; } catch (_) {}
    const root = doc.documentElement;
    let observedComposer, observedMain, observedBrand;
    const observer = new host.ResizeObserver(() => schedule());
    const schedule = () => {
        if (!frame && !disposed) frame = host.requestAnimationFrame(() => { frame = 0; measure(); });
    };
    const measure = () => {
        const main = doc.querySelector('.stMainBlockContainer');
        const composer = doc.querySelector('.st-key-dispatch_composer');
        const workspace = doc.querySelector('.st-key-dispatch_workspace');
        if (!main) return;
        if (main !== observedMain) { if (observedMain) observer.unobserve(observedMain); observer.observe(main); observedMain = main; }
        if (composer !== observedComposer) {
            if (observedComposer) observer.unobserve(observedComposer);
            if (composer) observer.observe(composer);
            observedComposer = composer;
        }
        const rect = main.getBoundingClientRect(), style = host.getComputedStyle(main);
        const sidebarContent = doc.querySelector('[data-testid="stSidebarUserContent"]');
        const brand = doc.querySelector('.st-key-sidebar_brand');
        if (sidebarContent && brand) {
            const bounds = sidebarContent.getBoundingClientRect();
            root.style.setProperty('--desk-sidebar-left', `${bounds.left}px`);
            root.style.setProperty('--desk-sidebar-width', `${bounds.width}px`);
            root.style.setProperty('--desk-sidebar-body-top', `${brand.parentElement.getBoundingClientRect().bottom + 12}px`);
            if (brand !== observedBrand) {
                if (observedBrand) observer.unobserve(observedBrand);
                observer.observe(brand); observedBrand = brand;
            }
        }
        root.style.setProperty('--desk-nav-left', `${rect.left + 8}px`);
        root.style.setProperty('--desk-input-left', `${rect.left + 8}px`);
        root.style.setProperty('--desk-input-width', `${Math.max(0, rect.width - 8 - parseFloat(style.paddingRight))}px`);
        const left = rect.left + parseFloat(style.paddingLeft) + 64;
        const width = Math.max(0, rect.width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) - 64);
        root.style.setProperty('--desk-left', `${left}px`);
        root.style.setProperty('--desk-width', `${width}px`);
        const composerHeight = composer?.getBoundingClientRect().height || 0;
        root.style.setProperty('--desk-composer-height', `${composerHeight}px`);
        root.style.setProperty('--desk-height', `${Math.max(120, host.innerHeight - 72 - composerHeight - 28)}px`);
        const pageNotice = doc.querySelector('.st-key-page_content .st-key-change_notice');
        const noticeSignature = pageNotice?.textContent;
        if (noticeSignature !== pageNoticeSignature) {
            if (pageNotice) pageNotice.scrollIntoView({block: 'start'});
            pageNoticeSignature = noticeSignature;
            host.__sweaterDeskLayout.pageNoticeSignature = noticeSignature;
        }
        if (!workspace) return;
        const response = workspace.querySelector('.st-key-response_pane');
        const signature = (response?.querySelector('h4')?.textContent || 'empty') +
            (response?.querySelector('.st-key-change_notice')?.textContent || '');
        if (response && signature !== responseSignature) {
            const hadPreviousResponse = responseSignature !== undefined;
            response.scrollTop = 0;
            if (hadPreviousResponse && host.innerWidth < 1000) response.scrollIntoView({block: 'start'});
            responseSignature = signature;
            host.__sweaterDeskLayout.responseSignature = signature;
        }
        const answer = workspace.querySelector('.st-key-response_pane')?.closest('[data-testid="stColumn"]');
        const orders = workspace.querySelector('.st-key-orders_pane')?.closest('[data-testid="stColumn"]');
        if (!answer || !orders || answer.parentElement !== orders.parentElement) return;
        const split = answer.parentElement;
        split.classList.add('desk-split');
        const minimum = Math.min(320, width * .4), maximum = Math.max(minimum, width - 360);
        const orderWidth = Math.max(minimum, Math.min(maximum, width * ratio));
        split.style.setProperty('--desk-orders-width', `${orderWidth}px`);
        const table = orders.querySelector('.st-key-orders_table');
        const ordersPane = orders.querySelector('.st-key-orders_pane');
        if (table && ordersPane) {
            const available = host.innerWidth >= 1000
                ? ordersPane.getBoundingClientRect().bottom - table.getBoundingClientRect().top - 16
                : Math.min(400, host.innerHeight * .45);
            root.style.setProperty('--desk-table-height', `${Math.max(100, available)}px`);
        }
        let handle = workspace.querySelector('.desk-resize-handle');
        if (!handle) {
            handle = doc.createElement('div');
            handle.className = 'desk-resize-handle'; handle.tabIndex = 0;
            handle.setAttribute('role', 'separator'); handle.setAttribute('aria-orientation', 'vertical');
            handle.setAttribute('aria-label', 'Resize order list');
            handle.title = 'Drag left to widen the order list · double-click to reset';
            workspace.appendChild(handle);
            handle.addEventListener('pointerdown', event => {
                if (event.button !== 0) return;
                const width = workspace.getBoundingClientRect().width;
                const minimum = Math.min(320, width * .4), maximum = Math.max(minimum, width - 360);
                event.preventDefault(); handle.setPointerCapture(event.pointerId);
                const move = e => {
                    const bounds = workspace.getBoundingClientRect();
                    ratio = Math.max(minimum, Math.min(maximum, bounds.right - e.clientX)) / width;
                    schedule();
                };
                const end = () => {
                    handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', end);
                    handle.removeEventListener('pointercancel', end);
                    try { host.sessionStorage.setItem('sweater-desk-order-width', String(ratio)); } catch (_) {}
                };
                handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', end);
                handle.addEventListener('pointercancel', end);
            });
            handle.addEventListener('dblclick', () => { ratio = .38; schedule(); try { host.sessionStorage.removeItem('sweater-desk-order-width'); } catch (_) {} });
            handle.addEventListener('keydown', event => {
                if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
                const width = workspace.getBoundingClientRect().width;
                const minimum = Math.min(320, width * .4), maximum = Math.max(minimum, width - 360);
                event.preventDefault();
                ratio = event.key === 'Home' ? .38 : ratio + (event.key === 'ArrowLeft' ? 24 : -24) / width;
                ratio = Math.max(minimum / width, Math.min(maximum / width, ratio));
                try { host.sessionStorage.setItem('sweater-desk-order-width', String(ratio)); } catch (_) {}
                schedule();
            });
        }
        handle.style.right = `${orderWidth + 2}px`;
        handle.setAttribute('aria-valuemin', String(Math.round(minimum)));
        handle.setAttribute('aria-valuemax', String(Math.round(maximum)));
        handle.setAttribute('aria-valuenow', String(Math.round(orderWidth)));
    };
    const mutations = new host.MutationObserver(schedule);
    mutations.observe(doc.querySelector('[data-testid="stAppViewContainer"]') || doc.body, {childList: true, subtree: true});
    host.addEventListener('resize', schedule);
    host.__sweaterDeskLayout = {responseSignature, pageNoticeSignature, dispose() {
        disposed = true; observer.disconnect(); mutations.disconnect(); host.removeEventListener('resize', schedule);
        if (frame) host.cancelAnimationFrame(frame);
        doc.querySelectorAll('.desk-resize-handle').forEach(handle => handle.remove());
    }};
    schedule();
})();
