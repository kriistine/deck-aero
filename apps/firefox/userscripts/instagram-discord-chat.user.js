// ==UserScript==
// @name         Instagram Discord-style chat
// @namespace    local.kris
// @version      1.6.1
// @description  Instagram DMs laid out like Discord: everyone on the left, name + timestamp above each run of messages, plain white text, no bubbles
// @match        https://www.instagram.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // Messages from the same person within this long are grouped under one header (Discord uses 7 min)
    const GROUP_MS = 7 * 60 * 1000;

    const css = `
    /* every message: left aligned, indented past the avatar column */
    main [data-aero-msg] {
        position: relative !important;
        padding-left: 72px !important;
        padding-right: 16px !important;
        box-sizing: border-box !important;
    }
    main [data-aero-msg][data-aero-first] { margin-top: 16px !important; }
    main [data-aero-msg]:hover { background: rgba(255, 255, 255, 0.04) !important; }
    /* Instagram's row: right-justified for your messages, so pin everything left */
    main [data-aero-msg] > div > div { justify-content: flex-start !important; }
    main [data-aero-msg] > div > div > div { flex-direction: row !important; justify-content: flex-start !important; }
    /* Instagram's own avatar column (incoming) and right-hand spacer (outgoing),
       only on the message's own row: replies add extra rows ("X replied to you",
       the quoted message) that must stay intact */
    main [data-aero-msg] > div > div:has([role="article"]) > div:not(:has([role="article"])) { display: none !important; }
    main [data-aero-msg] > div > div:not(:has([role="article"])) > div:empty { display: none !important; }

    /* no bubbles, plain white text */
    main [data-aero-msg] [role="article"] [role="presentation"] {
        background: transparent !important;
        background-image: none !important;
        border: none !important;
        box-shadow: none !important;
        padding: 1px 0 !important;
        border-radius: 0 !important;
    }
    main [data-aero-msg] [role="article"] [dir="auto"],
    main [data-aero-msg] [role="article"] [role="presentation"] span {
        color: #fff !important;
        text-align: left !important;
    }

    /* reactions: Instagram tucks them 16px up into the bubble's edge;
       with no bubble they should sit just under the message like Discord */
    main [data-aero-msg] .x2hkv1k { transform: translateY(4px) !important; }
    main [data-aero-msg]:has(.x2hkv1k) { padding-bottom: 22px !important; }  /* the pill overflows its 6px box */

    /* Instagram's own sender-name line in group chats (our header replaces it) */
    main [data-aero-msg] [data-aero-igname] { display: none !important; }

    /* replies to you / @mentions: Discord's gold highlight */
    main [data-aero-msg][data-aero-ping] {
        background: rgba(240, 177, 50, 0.08) !important;
        box-shadow: inset 2px 0 0 #f0b232 !important;
    }
    main [data-aero-msg][data-aero-ping]:hover { background: rgba(240, 177, 50, 0.12) !important; }

    /* collapsible Notes row in the chat list (Discord category header style) */
    .aero-notes-toggle {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 24px;
        height: 20px;
        align-self: center;
        border-radius: 4px;
        color: #3daee9;
        cursor: pointer;
        user-select: none;
    }
    .aero-notes-toggle[data-collapsed] { color: rgba(255, 255, 255, 0.5); }
    .aero-notes-toggle:hover { color: #fff; background: rgba(255, 255, 255, 0.1); }
    .aero-notes-toggle svg { width: 16px; height: 16px; transition: transform 0.15s ease; }
    /* down arrow while hidden, up arrow while showing */
    .aero-notes-toggle:not([data-collapsed]) svg { transform: rotate(180deg); }
    [data-aero-notes][data-collapsed] { display: none !important; }

    /* pinned messages: no strip under the header; a pin button opens it as a
       dropdown, like Discord's pinned-messages popout */
    [data-aero-pinbar] { display: none !important; }
    html[data-aero-pins-open] [data-aero-pinbar] {
        display: flex !important;
        position: absolute !important;
        top: 6px !important;
        right: 12px !important;
        width: min(460px, calc(100% - 24px)) !important;
        z-index: 30 !important;
        background: rgba(15, 15, 15, 0.97) !important;
        border: 1px solid #000 !important;
        border-radius: 6px !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1), 0 8px 24px rgba(0, 0, 0, 0.6) !important;
    }
    .aero-pin-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        margin: 0 3px;
        box-sizing: border-box;
        color: #fff;
        cursor: pointer;
        background: linear-gradient(to bottom, #4a4a4a 0%, #2b2b2b 49%, #000000 50%, #111111 100%);
        border: 1px solid #000;
        border-radius: 6px;
        box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.25), 0 1px 2px rgba(0, 0, 0, 0.5);
    }
    .aero-pin-btn:hover { background: linear-gradient(to bottom, #666666 0%, #444444 49%, #1a1a1a 50%, #2b2b2b 100%); }
    html[data-aero-pins-open] .aero-pin-btn {
        background: linear-gradient(to bottom, #000000 0%, #151515 100%);
        box-shadow: inset 0 2px 5px rgba(0, 0, 0, 0.9);
        color: #3daee9;
    }
    .aero-pin-btn svg { width: 18px; height: 18px; }

    /* header: avatar, name, time */
    .aero-hdr {
        display: flex;
        align-items: baseline;
        gap: 8px;
        line-height: 20px;
        margin-bottom: 1px;
    }
    .aero-av {
        position: absolute;
        left: 16px;
        top: 2px;
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: #333 center / cover no-repeat;
    }
    .aero-name { color: #fff; font-weight: 600; font-size: 15px; }
    .aero-name.aero-me { color: #3daee9; }
    .aero-time { color: rgba(255, 255, 255, 0.5); font-size: 12px; }
    /* continuation lines: time appears in the avatar gutter on hover */
    .aero-gut {
        position: absolute;
        left: 0;
        width: 64px;
        top: 50%;
        transform: translateY(-50%);
        text-align: center;
        font-size: 11px;
        color: rgba(255, 255, 255, 0.5);
        opacity: 0;
        pointer-events: none;
    }
    main [data-aero-msg]:hover > .aero-gut { opacity: 1; }
    `;
    const style = document.createElement('style');
    style.id = 'aero-discord-chat';
    style.textContent = css;
    (document.head || document.documentElement).appendChild(style);

    const fiberOf = (el) => {
        const k = Object.keys(el).find((k) => k.startsWith('__reactFiber'));
        return k && el[k];
    };

    // { outgoing, sender, ts } straight from Instagram's React props for the message row
    function messageInfo(group) {
        const art = group.querySelector('[role="article"]');
        if (!art) return null;
        let f = fiberOf(art);
        let info = null;
        for (let i = 0; i < 60 && f; i++, f = f.return) {
            const p = f.memoizedProps;
            if (!p) continue;
            if (!info && p.slideMessageRef && 'outgoing' in p) {
                info = {
                    outgoing: !!p.outgoing,
                    sender: String(p.slideMessageRef.sender_fbid || ''),
                    ts: Number(p.slideMessageRef.timestamp_ms) || 0,
                    isGroup: !!(p.threadRef && p.threadRef.is_group),
                    prevSender: null,
                };
            }
            // further up, the row knows who sent the message before it (even if that one isn't rendered)
            if (info && 'previousMessageRef' in p) {
                info.prevSender = p.previousMessageRef ? String(p.previousMessageRef.sender_fbid || '') : '';
                break;
            }
        }
        return info;
    }

    // ---- who is who -------------------------------------------------------
    const people = new Map(); // sender fbid -> { name, avatar }

    function me() {
        const a = [...document.querySelectorAll('a[href]')].find((a) => /\bProfile\b/.test(a.textContent) || a.querySelector('img[alt*="profile picture" i]'));
        const name = a ? a.getAttribute('href').replace(/\//g, '') : 'You';
        const img = a && a.querySelector('img');
        return { name, avatar: img ? img.src : '' };
    }

    function chatHeader() {
        const info = document.querySelector('svg[aria-label="Conversation information"]');
        let h = info;
        for (let i = 0; i < 12 && h && !h.querySelector('a[href] img'); i++) h = h.parentElement;
        if (!h) return null;
        const a = h.querySelector('a[href] img').closest('a');
        // display name: first visible text in the header that isn't the "Active ..." line
        const texts = [...h.querySelectorAll('span, h1, h2')]
            .filter((e) => !e.children.length)
            .map((e) => e.textContent.trim())
            .filter((t) => t && !/^Active|^Typing/i.test(t));
        return { name: texts[0] || a.getAttribute('href').replace(/\//g, ''), avatar: a.querySelector('img').src };
    }

    function learn(group, info) {
        // Instagram puts a profile link + avatar next to the other person's messages
        const a = group.querySelector('a[href^="/"] img');
        if (a && !info.outgoing && !people.has(info.sender)) {
            const link = a.closest('a');
            people.set(info.sender, { name: link.getAttribute('href').replace(/\//g, ''), avatar: a.src });
        }
    }

    function personFor(info) {
        if (info.outgoing) return me();
        if (!info.isGroup) {
            const h = chatHeader();
            if (h) return h;
        }
        return people.get(info.sender) || { name: 'Unknown', avatar: '' };
    }

    // Rows above the message itself are either Instagram's sender-name line, or the
    // "X replied to ..." label + quoted message of a reply. The name line is plain
    // text: no buttons, no images, no "replied".
    function hideInstagramName(group) {
        const l1 = [...group.children].find((c) => !/^aero-/.test(c.className));
        if (!l1) return;
        for (const row of l1.children) {
            if (row.querySelector('[role="article"]')) break;
            const text = row.textContent.trim();
            if (text && !row.querySelector('[role="button"], img, video') && !/\breplied\b/i.test(text)) {
                row.dataset.aeroIgname = '';
            }
        }
    }

    function pingsMe(group, name) {
        // Instagram labels replies "<name> replied to you" above the quoted message
        const replied = [...group.querySelectorAll('span, div')].some(
            (e) => !e.children.length && /\breplied to you\b/i.test(e.textContent)
        );
        if (replied) return true;
        const art = group.querySelector('[role="article"]');
        return !!(art && name && new RegExp('@' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'i').test(art.textContent));
    }

    // ---- time formatting (Discord style) ----------------------------------
    const clock = (d) => d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    // today: just the time; anything older: just the date
    function stamp(ts) {
        const d = new Date(ts);
        return d.toDateString() === new Date().toDateString() ? clock(d) : d.toLocaleDateString();
    }

    // ---- decorate -----------------------------------------------------------
    function decorate() {
        const groups = [...document.querySelectorAll('main [role="group"]')].filter(
            (g) => !g.parentElement.closest('[role="group"]')
        );
        let prev = null;
        const myName = me().name;
        for (const g of groups) {
            const info = messageInfo(g);
            if (!info) { prev = null; continue; }
            // only compare with the group directly above if it really is the previous message
            if (prev && info.prevSender !== null && prev.sender !== info.prevSender) prev = null;
            learn(g, info);
            const first = prev
                ? prev.sender !== info.sender || info.ts - prev.ts > GROUP_MS
                : info.prevSender !== info.sender;
            const key = info.sender + ':' + info.ts + ':' + first;
            prev = info;

            // highlight when someone replies to you or @mentions you
            const ping = !info.outgoing && pingsMe(g, myName);
            if (ping) g.dataset.aeroPing = ''; else delete g.dataset.aeroPing;

            hideInstagramName(g);
            sizeMedia(g);

            if (g.dataset.aeroMsg === key) continue;

            g.dataset.aeroMsg = key;
            if (info.outgoing) g.dataset.aeroOut = ''; else delete g.dataset.aeroOut;
            g.querySelectorAll(':scope > .aero-hdr, :scope > .aero-gut, :scope > .aero-av').forEach((e) => e.remove());

            if (first) {
                g.dataset.aeroFirst = '';
                const who = personFor(info);
                const av = document.createElement('div');
                av.className = 'aero-av';
                if (who.avatar) av.style.backgroundImage = `url("${who.avatar}")`;
                const hdr = document.createElement('div');
                hdr.className = 'aero-hdr';
                const name = document.createElement('span');
                name.className = 'aero-name' + (info.outgoing ? ' aero-me' : '');
                name.textContent = who.name;
                const time = document.createElement('span');
                time.className = 'aero-time';
                time.textContent = info.ts ? stamp(info.ts) : '';
                hdr.append(name, time);
                g.prepend(av, hdr);
            } else {
                delete g.dataset.aeroFirst;
                const gut = document.createElement('span');
                gut.className = 'aero-gut';
                gut.textContent = info.ts ? clock(new Date(info.ts)) : '';
                g.prepend(gut);
            }
        }
    }

    // ---- media: Discord-sized (up to 400 x 350, own aspect ratio, 8px corners) ----
    const MEDIA_W = 400, MEDIA_H = 350;
    function sizeMedia(group) {
        for (const box of group.querySelectorAll('[style*="--x-maxWidth"]')) {
            if (box.dataset.aeroMedia) continue;
            // Instagram keeps the aspect ratio as padding-bottom % on the child
            const pad = box.querySelector('[style*="--x-paddingBottom"]');
            const m = pad && /--x-paddingBottom:\s*([\d.]+)%/.exec(pad.getAttribute('style'));
            if (!m) continue;
            const ratio = 100 / parseFloat(m[1]); // width / height
            // fixed px only: a % cap is ignored when the wrappers size to content, so they'd stretch to the full image width
            box.style.setProperty('max-width', `min(${MEDIA_W}px, ${Math.round(MEDIA_H * ratio)}px)`, 'important');
            box.style.setProperty('max-height', 'none', 'important');
            box.dataset.aeroMedia = '';
            // Instagram's 18px rounding sits on the clipping wrapper and its overlay
            const art = box.closest('[role="article"]');
            for (let e = box; e && e !== art; e = e.parentElement) {
                if (parseFloat(getComputedStyle(e).borderTopLeftRadius) >= 12) {
                    e.style.setProperty('border-radius', '8px', 'important');
                    for (const sib of e.children) {
                        if (parseFloat(getComputedStyle(sib).borderTopLeftRadius) >= 12) sib.style.setProperty('border-radius', '8px', 'important');
                    }
                }
            }
        }
    }

    // ---- collapsible notes ----------------------------------------------------
    const NOTES_KEY = 'aeroNotesCollapsed';
    const notesCollapsed = () => {
        try { return localStorage.getItem(NOTES_KEY) !== '0'; } catch (e) { return true; } // hidden by default
    };

    function notesBox() {
        const tl = document.querySelector('[aria-label="Thread list"]');
        if (!tl) return null;
        // the notes carousel is the list of <li> bubbles; climb to the block that sits
        // beside the "Messages / Requests" heading
        const ul = [...tl.querySelectorAll('ul')].find((u) => u.querySelector('li [role="button"]') && /note/i.test(u.textContent));
        if (!ul) return null;
        let e = ul;
        while (e.parentElement && e.parentElement !== tl && !/Requests/.test(e.parentElement.textContent.replace(e.textContent, ''))) {
            e = e.parentElement;
        }
        return e.parentElement && e.parentElement !== tl ? e : null;
    }

    function setupNotes() {
        const box = notesBox();
        if (!box) return;
        box.dataset.aeroNotes = '';
        // the toggle lives in the "Messages ... Requests" heading row, between the two
        const heading = [...document.querySelectorAll('[aria-label="Thread list"] h1')].find((h) => h.textContent.trim() === 'Messages');
        const row = heading && heading.parentElement;
        if (!row) return;
        let t = row.querySelector(':scope > .aero-notes-toggle');
        if (!t) {
            t = document.createElement('div');
            t.className = 'aero-notes-toggle';
            t.title = 'Show / hide notes';
            t.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';
            t.addEventListener('click', () => {
                try { localStorage.setItem(NOTES_KEY, notesCollapsed() ? '0' : '1'); } catch (e) {}
                setupNotes();
            });
            heading.after(t);
        }
        const c = notesCollapsed();
        t.toggleAttribute('data-collapsed', c);
        box.toggleAttribute('data-collapsed', c);
    }

    // ---- pinned messages -------------------------------------------------------
    let pinsPath = location.pathname;
    function setupPins() {
        // switching chats closes the dropdown
        if (location.pathname !== pinsPath) {
            pinsPath = location.pathname;
            delete document.documentElement.dataset.aeroPinsOpen;
        }
        // the strip is the row holding the pin icon and the prev/next arrows
        const icon = document.querySelector('main svg[aria-label="Pinned message icon"]');
        let bar = null;
        if (icon) {
            bar = icon;
            const next = document.querySelector('main svg[aria-label="Next pinned message"]');
            while (bar && next && !bar.contains(next)) bar = bar.parentElement;
            if (bar && bar.parentElement) bar = bar.parentElement; // the full-width row around it
            if (bar) bar.dataset.aeroPinbar = '';
        }

        const call = document.querySelector('main svg[aria-label="Audio call"]');
        const info = document.querySelector('main svg[aria-label="Conversation information"]');
        let btn = document.querySelector('.aero-pin-btn');
        if (!bar || !call || !info) {
            if (btn) btn.remove();
            return;
        }
        if (btn) return;
        // header buttons: insert before the call button's wrapper in the row they share
        let slot = call.closest('[role="button"]');
        while (slot && slot.parentElement && !slot.parentElement.contains(info)) slot = slot.parentElement;
        if (!slot) return;
        btn = document.createElement('div');
        btn.className = 'aero-pin-btn';
        btn.setAttribute('role', 'button');
        btn.title = 'Pinned messages';
        btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5"/><path d="M9 10.8a2 2 0 0 1-1.1 1.8l-1.8.9A2 2 0 0 0 5 15.2V17h14v-1.8a2 2 0 0 0-1.1-1.8l-1.8-.9a2 2 0 0 1-1.1-1.8V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>';
        btn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            document.documentElement.toggleAttribute('data-aero-pins-open');
        });
        slot.before(btn);
    }
    // clicking anywhere outside the dropdown closes it
    document.addEventListener('click', (ev) => {
        if (!document.documentElement.hasAttribute('data-aero-pins-open')) return;
        if (ev.target.closest('[data-aero-pinbar], .aero-pin-btn')) return;
        delete document.documentElement.dataset.aeroPinsOpen;
    }, true);

    let queued = false;
    new MutationObserver(() => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => { queued = false; decorate(); setupNotes(); setupPins(); });
    }).observe(document.body, { childList: true, subtree: true });
    decorate();
    setupNotes();
    setupPins();
})();
