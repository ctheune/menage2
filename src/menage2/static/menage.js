
function isGroupCollapsed(tag) {
    if (!tag) return false;
    var header = document.querySelector('.tag-group-header[data-tag="' + tag + '"]');
    if (header && header.dataset.open === 'false') return true;
    var colon = tag.lastIndexOf(':');
    if (colon > -1) return isGroupCollapsed(tag.slice(0, colon));
    return false;
}

function applyGroupVisibility() {
    document.querySelectorAll('[data-parent-tag]').forEach(function(el) {
        el.style.display = isGroupCollapsed(el.dataset.parentTag) ? 'none' : '';
    });
}

function toggleGroup(tag) {
    var header = document.querySelector('.tag-group-header[data-tag="' + tag + '"]');
    if (!header) return;
    header.dataset.open = header.dataset.open === 'false' ? 'true' : 'false';
    applyGroupVisibility();
}

function setAllGroups(open) {
    document.querySelectorAll('.tag-group-header').forEach(function(h) {
        h.dataset.open = open ? 'true' : 'false';
    });
    applyGroupVisibility();
}

document.addEventListener('click', function(e) {
    var header = e.target.closest('.tag-group-header');
    if (header) toggleGroup(header.dataset.tag);
});

function swipePost(url, todoId, list) {
    htmx.ajax('POST', url, {target: list, swap: 'innerHTML swap:120ms', values: {todo_ids: todoId}});
}

function initSortables(content) {
    var sortables = content.querySelectorAll(".sortable");
    for (var i = 0; i < sortables.length; i++) {
      var sortable = sortables[i];
      new Sortable(sortable, {
          animation: 150,
          filter: '.non-sortable', // 'filtered' class is not draggable
          ghostClass: 'bg-blue-200'
      });
    }
}

var _swipeTouchState = new WeakMap();
var _SWIPE_THRESHOLD = 80;

document.addEventListener('touchstart', function(e) {
    var item = e.target.closest('.todo-item');
    if (!item) return;
    var inner = item.querySelector('.todo-content');
    if (!inner) return;
    inner.style.transition = 'none';
    _swipeTouchState.set(item, {startX: e.touches[0].clientX, dx: 0});
}, {passive: true});

document.addEventListener('touchmove', function(e) {
    var item = e.target.closest('.todo-item');
    if (!item) return;
    var state = _swipeTouchState.get(item);
    if (!state) return;
    var inner = item.querySelector('.todo-content');
    if (!inner) return;
    state.dx = e.touches[0].clientX - state.startX;
    inner.style.transform = 'translateX(' + Math.max(-150, Math.min(150, state.dx)) + 'px)';
    item.dataset.swipeDir = state.dx > 0 ? 'right' : (state.dx < 0 ? 'left' : '');
}, {passive: true});

document.addEventListener('touchend', function(e) {
    var item = e.target.closest('.todo-item');
    if (!item) return;
    var state = _swipeTouchState.get(item);
    if (!state) return;
    _swipeTouchState.delete(item);
    var inner = item.querySelector('.todo-content');
    if (!inner) return;
    inner.style.transition = 'transform 0.2s ease';
    var dx = state.dx;
    var list = document.getElementById('todo-list');
    var checkbox = item.querySelector('.todo-checkbox');
    var todoId = checkbox ? checkbox.dataset.id : null;
    if (dx >= _SWIPE_THRESHOLD && list && todoId) {
        inner.style.transform = 'translateX(100vw)';
        swipePost(list.dataset.doneUrl, todoId, list);
    } else if (dx <= -_SWIPE_THRESHOLD && list && todoId) {
        inner.style.transform = 'translateX(-100vw)';
        swipePost(list.dataset.holdUrl, todoId, list);
    } else {
        inner.style.transform = 'translateX(0)';
        delete item.dataset.swipeDir;
    }
});

function initTodoSwipe() {} // kept for htmx.onLoad call below; delegation handles all items

function parseTagsFromRaw(raw) {
    var tagMatches = (raw.match(/#\S+/g) || []).map(function(t) { return t.slice(1); });
    var text = raw.replace(/#\S+/g, '').replace(/\s+/g, ' ').trim();
    return { tags: tagMatches, text: text };
}

// Delegated handler: clicking a todo-item row toggles its checkbox
document.addEventListener('click', function(e) {
    var item = e.target.closest('.todo-item');
    if (!item) return;
    if (e.target.closest('.todo-edit-btn')) return;
    var checkbox = item.querySelector('.todo-checkbox');
    if (!checkbox || e.target === checkbox) return;
    checkbox.checked = !checkbox.checked;
});

// Delegated handler for the edit pencil button \u2014 fires todoEditStart event
document.addEventListener('click', function(e) {
    var btn = e.target.closest('.todo-edit-btn');
    if (!btn) return;
    e.stopPropagation();
    var li = btn.closest('li[id^="todo-"]');
    if (!li) return;
    document.dispatchEvent(new CustomEvent('todoEditStart', {detail: {
        id: li.id.replace('todo-', ''),
        text: li.dataset.todoText || '',
        tags: (li.dataset.todoTags || '').split(',').filter(Boolean),
        dueDate: li.dataset.dueDate || null,
        recurrence: li.dataset.recurrence || null,
        editUrl: li.dataset.editUrl || ''
    }}));
});

function initTagInput() {
    var container = document.getElementById('todo-tag-input');
    if (!container || container.dataset.tagInputInit) return;
    container.dataset.tagInputInit = '1';

    var textOuter = document.getElementById('todo-text');
    var form = document.getElementById('todo-form');
    var quickPick = document.getElementById('todo-quick-pick');

    var tags = JSON.parse(sessionStorage.getItem('todo-tags') || '[]');
    var addUrl = form.getAttribute('hx-post');
    var savedTags = null;
    var savedDateISO = null;
    var savedRecLabel = null;
    var savedNoteText = null;
    var editingId = null;
    var dateISO = null;
    var dateLabel = null;
    var recLabel = null;
    var noteText = '';
    var _placeholder = 'New todo\u2026';

    // --- Segment helpers ---
    // DOM structure: [span.todo-text-seg] [span.pill] [span.todo-text-seg] [span.pill] ...
    // Pills sit inline between editable segments; empty segs between pills give the cursor
    // a place to land, creating one virtual textfield.

    function createTextSeg(text) {
        var seg = document.createElement('span');
        seg.className = 'todo-text-seg';
        seg.contentEditable = 'true';
        seg.setAttribute('spellcheck', 'true');
        seg.setAttribute('enterkeyhint', 'done');
        if (text) seg.textContent = text;
        return seg;
    }

    function getAllSegs() { return Array.from(textOuter.querySelectorAll('.todo-text-seg')); }

    function getActiveSeg() {
        var a = document.activeElement;
        return (a && a.classList.contains('todo-text-seg') && textOuter.contains(a)) ? a : null;
    }

    function getFirstSeg() { return textOuter.querySelector('.todo-text-seg'); }
    function getLastSeg() { var s = getAllSegs(); return s[s.length - 1] || null; }

    function placeCursorAtEnd(seg) {
        var range = document.createRange(), sel = window.getSelection();
        range.selectNodeContents(seg); range.collapse(false);
        if (sel) { sel.removeAllRanges(); sel.addRange(range); }
    }

    function placeCursorAtStart(seg) {
        var range = document.createRange(), sel = window.getSelection();
        range.setStart(seg, 0); range.collapse(true);
        if (sel) { sel.removeAllRanges(); sel.addRange(range); }
    }

    function focusFirstSeg() { var s = getFirstSeg(); if (s) { s.focus(); placeCursorAtEnd(s); } }
    function focusLastSeg()  { var s = getLastSeg();  if (s) { s.focus(); placeCursorAtEnd(s); } }

    function isAtEnd(seg) {
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount || !sel.getRangeAt(0).collapsed) return false;
        var cursor = sel.getRangeAt(0);
        if (!seg.contains(cursor.startContainer)) return false;
        try {
            var test = document.createRange();
            test.setStart(cursor.startContainer, cursor.startOffset);
            test.setEnd(seg, seg.childNodes.length);
            return test.toString() === '';
        } catch (e) { return false; }
    }

    function isAtStart(seg) {
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount || !sel.getRangeAt(0).collapsed) return false;
        var cursor = sel.getRangeAt(0);
        if (!seg.contains(cursor.startContainer)) return false;
        try {
            var test = document.createRange();
            test.setStart(seg, 0);
            test.setEnd(cursor.startContainer, cursor.startOffset);
            return test.toString() === '';
        } catch (e) { return false; }
    }

    // --- ContentEditable helpers ---

    function getPlainText() {
        return getAllSegs().map(function(s) { return s.textContent; }).join('').replace(/\s+/g, ' ').trim();
    }

    function getTextBeforeCursor() {
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) return '';
        var range = sel.getRangeAt(0);
        var activeSeg = getActiveSeg();
        if (!activeSeg) return '';
        var text = '';
        var segs = getAllSegs();
        for (var i = 0; i < segs.length; i++) {
            if (segs[i] !== activeSeg) { text += segs[i].textContent; continue; }
            var anchor = range.startContainer, offset = range.startOffset;
            if (anchor === activeSeg) {
                for (var j = 0; j < offset; j++) {
                    var c = activeSeg.childNodes[j];
                    if (c && c.nodeType === Node.TEXT_NODE) text += c.textContent;
                }
            } else {
                var node = activeSeg.firstChild;
                while (node) {
                    if (node === anchor) { if (node.nodeType === Node.TEXT_NODE) text += node.textContent.slice(0, offset); break; }
                    if (node.nodeType === Node.TEXT_NODE) text += node.textContent;
                    node = node.nextSibling;
                }
            }
            break;
        }
        return text;
    }

    function updateEmptyClass() {
        var first = getFirstSeg();
        if (!first) return;
        var hasContent = getPlainText().length > 0 || !!textOuter.querySelector('[data-pill]');
        first.classList.toggle('todo-input-empty', !hasContent);
    }

    // --- Pill factories ---

    function createTagPill(tag) {
        var pill = document.createElement('span');
        pill.className = 'todo-tag-pill';
        pill.dataset.pill = 'tag';
        pill.dataset.tag = tag;
        pill.innerHTML = '#' + tag + ' <button class="todo-tag-remove" type="button" tabindex="-1" data-tag="' + tag + '">\xd7</button>';
        return pill;
    }

    function createDatePill() {
        var label = dateLabel || _formatDateLabel(dateISO);
        var pill = document.createElement('span');
        pill.className = 'todo-date-pill';
        pill.dataset.pill = 'date';
        pill.dataset.iso = dateISO;
        pill.title = dateISO;
        pill.innerHTML = '\u2197 ' + label + ' <button class="todo-date-remove" type="button" tabindex="-1" title="Remove date">\xd7</button>';
        return pill;
    }

    function createRecPill() {
        var pill = document.createElement('span');
        pill.className = 'todo-rec-pill';
        pill.dataset.pill = 'rec';
        pill.dataset.label = recLabel;
        pill.title = recLabel;
        pill.innerHTML = '\u21bb ' + recLabel + ' <button class="todo-rec-remove" type="button" tabindex="-1" title="Remove repeat">\xd7</button>';
        return pill;
    }

    function createNotePill() {
        var pill = document.createElement('span');
        pill.className = 'todo-note-pill';
        pill.dataset.pill = 'note';
        pill.title = noteText;
        pill.innerHTML = '~ ' + noteText + ' <button class="todo-note-remove" type="button" tabindex="-1" title="Remove note">\xd7</button>';
        return pill;
    }

    // Rebuild DOM: [seg(text)] [pill] [empty-seg] [pill] [empty-seg] ...
    // Pills are inline between editable spans; passing overrideText replaces first-seg content.
    function renderAllPills(overrideText) {
        var hadFocus = textOuter.contains(document.activeElement);
        var first = getFirstSeg();
        var rawSaved = overrideText !== undefined ? overrideText : (first ? first.textContent : '');

        // Build pill list first so we know whether to add a trailing space
        var pillList = [];
        tags.forEach(function(tag) { pillList.push(createTagPill(tag)); });
        if (dateISO) pillList.push(createDatePill());
        if (recLabel) pillList.push(createRecPill());
        if (noteText) pillList.push(createNotePill());

        // Normalize: collapse \u00a0, trim trailing whitespace, add exactly one
        // trailing space as separator when pills follow non-empty text
        var savedText = rawSaved.replace(/\u00a0/g, ' ').trimEnd();
        if (pillList.length > 0 && savedText.length > 0) savedText += ' ';

        textOuter.innerHTML = '';

        var firstSeg = createTextSeg(savedText);
        firstSeg.dataset.placeholder = _placeholder;
        textOuter.appendChild(firstSeg);

        pillList.forEach(function(pill) {
            textOuter.appendChild(pill);
            textOuter.appendChild(createTextSeg(''));
        });

        sessionStorage.setItem('todo-tags', JSON.stringify(tags));
        updateEmptyClass();
        if (hadFocus) focusLastSeg();
    }

    // --- Quick pick row ---

    function renderQuickPick() {
        if (!quickPick) return;
        quickPick.innerHTML = '';
        var available = Array.from(document.querySelectorAll('.tag-group-header[data-tag]'))
            .map(function(el) { return el.dataset.tag; })
            .filter(function(t) { return t && t !== '__untagged__' && tags.indexOf(t) === -1; })
            .sort();
        available.forEach(function(tag) {
            var chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'todo-quick-pick-chip';
            chip.textContent = '#' + tag;
            chip.addEventListener('click', function() { addTag(tag); });
            quickPick.appendChild(chip);
        });
    }

    function showQuickPick() { if (quickPick && quickPick.children.length > 0) quickPick.style.display = ''; }
    function hideQuickPick() { if (quickPick) quickPick.style.display = 'none'; }

    hideQuickPick();
    textOuter.addEventListener('focusin', function(e) {
        if (e.target.classList.contains('todo-text-seg')) showQuickPick();
    });
    textOuter.addEventListener('focusout', function() {
        setTimeout(function() { if (!textOuter.contains(document.activeElement)) hideQuickPick(); }, 150);
    });

    // --- Tag state ---

    function addTag(tag) {
        tag = tag.replace(/^#/, '');
        if (tags.indexOf(tag) === -1) { tags.push(tag); renderAllPills(); renderQuickPick(); }
        focusLastSeg();
    }

    function removeTag(tag) {
        tags = tags.filter(function(t) { return t !== tag; });
        renderAllPills(); renderQuickPick(); focusLastSeg();
    }

    // --- Date state ---

    function _formatDateLabel(iso) {
        var d = new Date(iso + 'T00:00:00');
        var weekday = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()];
        var month = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()];
        return weekday + ', ' + d.getDate() + ' ' + month;
    }

    function setDate(iso, label) { dateISO = iso || null; dateLabel = label || null; renderAllPills(); }
    function clearDate() { setDate(null, null); }

    function openDatePillPicker() {
        openPicker({ anchorEl: container, initialISO: dateISO, title: 'When is this due?',
            onCommit: function(iso) { setDate(iso, null); focusLastSeg(); },
            onCancel: function() { focusLastSeg(); } });
    }

    // --- Recurrence state ---

    function setRecurrence(label) { recLabel = label || null; renderAllPills(); }
    function clearRecurrence() { setRecurrence(null); }

    function openRecurrencePillPicker() {
        openRecurrencePicker({ anchorEl: container, initialLabel: recLabel, title: 'Repeat',
            onCommit: function(label) { setRecurrence(label); focusLastSeg(); },
            onCancel: function() { focusLastSeg(); } });
    }

    // --- Note state ---

    function setNote(text) { noteText = text || ''; renderAllPills(); }
    function clearNote() { setNote(''); }

    function openNotePillPicker() {
        openNotePicker({ anchorEl: container, initialNote: noteText, title: 'Note',
            onCommit: function(text) { setNote(text); focusLastSeg(); },
            onCancel: function() { focusLastSeg(); } });
    }

    function removePillFromState(el) {
        if (el.dataset.pill === 'tag') removeTag(el.dataset.tag);
        else if (el.dataset.pill === 'date') clearDate();
        else if (el.dataset.pill === 'rec') clearRecurrence();
        else if (el.dataset.pill === 'note') clearNote();
    }

    // --- Click handler ---

    container.addEventListener('click', function(e) {
        var rmTag = e.target.closest('.todo-tag-remove');
        if (rmTag) { e.stopPropagation(); removeTag(rmTag.dataset.tag); return; }
        var rmDate = e.target.closest('.todo-date-remove');
        if (rmDate) { e.stopPropagation(); clearDate(); focusLastSeg(); return; }
        var datePill = e.target.closest('.todo-date-pill');
        if (datePill) { e.stopPropagation(); openDatePillPicker(); return; }
        var rmRec = e.target.closest('.todo-rec-remove');
        if (rmRec) { e.stopPropagation(); clearRecurrence(); focusLastSeg(); return; }
        var recPill = e.target.closest('.todo-rec-pill');
        if (recPill) { e.stopPropagation(); openRecurrencePillPicker(); return; }
        var rmNote = e.target.closest('.todo-note-remove');
        if (rmNote) { e.stopPropagation(); clearNote(); focusLastSeg(); return; }
        var notePill = e.target.closest('.todo-note-pill');
        if (notePill) { e.stopPropagation(); openNotePillPicker(); return; }
        if (e.target.closest('.todo-tag-pill')) return;
        if (!e.target.classList.contains('todo-text-seg')) focusLastSeg();
    });

    // --- Autocomplete ---

    var acEl = document.createElement('div');
    acEl.className = 'todo-tag-autocomplete';
    acEl.style.display = 'none';
    form.style.position = 'relative';
    form.appendChild(acEl);
    var acSelected = -1;

    function acItems() { return Array.from(acEl.querySelectorAll('.todo-ac-item')); }
    function hideAc() { acEl.style.display = 'none'; acSelected = -1; }

    function showAc(matches) {
        if (!matches.length) { hideAc(); return; }
        acSelected = -1;
        acEl.innerHTML = '';
        matches.forEach(function(tag) {
            var item = document.createElement('div');
            item.className = 'todo-ac-item';
            item.textContent = '#' + tag;
            item.dataset.tag = tag;
            item.addEventListener('mousedown', function(e) { e.preventDefault(); selectAc(tag); });
            acEl.appendChild(item);
        });
        acEl.style.display = 'block';
    }

    function selectAc(tag) {
        var sel = window.getSelection();
        if (sel && sel.rangeCount) {
            var range = sel.getRangeAt(0);
            if (range.startContainer.nodeType === Node.TEXT_NODE) {
                var tn = range.startContainer, pos = range.startOffset;
                var newBefore = tn.textContent.slice(0, pos).replace(/#\S*$/, '');
                tn.textContent = newBefore + tn.textContent.slice(pos);
                range.setStart(tn, newBefore.length); range.collapse(true);
                sel.removeAllRanges(); sel.addRange(range);
            }
        }
        hideAc();
        addTag(tag);
    }

    function fuzzyScore(fragment, tag) {
        if (!fragment) return 2;
        var f = fragment.toLowerCase(), t = tag.toLowerCase();
        if (t.startsWith(f)) return 0;
        if (t.split(':').some(function(s) { return s.startsWith(f); })) return 1;
        var fi = 0;
        for (var ti = 0; ti < t.length && fi < f.length; ti++) { if (t[ti] === f[fi]) fi++; }
        return fi === f.length ? 2 : -1;
    }

    function updateAc() {
        var textBefore = getTextBeforeCursor();
        var m = textBefore.match(/#(\S*)$/);
        if (!m) { hideAc(); return; }
        var fragment = m[1];
        var known = Array.from(document.querySelectorAll('.tag-group-header[data-tag]'))
            .map(function(el) { return el.dataset.tag; })
            .filter(function(t) { return t && t !== '__untagged__' && tags.indexOf(t) === -1; });
        var scored = [];
        known.forEach(function(t) { var s = fuzzyScore(fragment, t); if (s >= 0) scored.push({tag: t, score: s}); });
        scored.sort(function(a, b) { return a.score - b.score || a.tag.localeCompare(b.tag); });
        showAc(scored.map(function(x) { return x.tag; }));
    }

    // --- Keyboard handling (delegated to textOuter) ---

    textOuter.addEventListener('keydown', function(e) {
        var activeSeg = getActiveSeg();
        if (!activeSeg) return;
        var items = acItems();

        // Autocomplete navigation takes priority
        if (acEl.style.display !== 'none' && items.length) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                acSelected = Math.min(acSelected + 1, items.length - 1);
                items.forEach(function(el, i) { el.classList.toggle('todo-ac-selected', i === acSelected); });
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                acSelected = Math.max(acSelected - 1, -1);
                items.forEach(function(el, i) { el.classList.toggle('todo-ac-selected', i === acSelected); });
                return;
            }
            if ((e.key === 'Enter' || e.key === 'Tab') && acSelected >= 0) {
                e.preventDefault(); selectAc(items[acSelected].dataset.tag); return;
            }
            if (e.key === 'Tab' && acSelected < 0 && items.length) {
                e.preventDefault(); selectAc(items[0].dataset.tag); return;
            }
            if (e.key === 'Escape') { hideAc(); return; }
        }

        if (e.key === 'Enter') {
            e.preventDefault();
            form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
            return;
        }

        if (e.key === 'Escape') {
            if (editingId) exitEditMode();
            activeSeg.blur();
            return;
        }

        // Cross-seg arrow navigation
        var segs = getAllSegs(), idx = segs.indexOf(activeSeg);

        if (e.key === 'ArrowRight' && e.metaKey) {
            e.preventDefault(); focusLastSeg(); return;
        }
        if (e.key === 'ArrowLeft' && e.metaKey) {
            e.preventDefault();
            var first = getFirstSeg();
            if (first) { first.focus(); placeCursorAtStart(first); }
            return;
        }
        if (e.key === 'a' && e.metaKey) {
            e.preventDefault();
            var first = getFirstSeg(), last = getLastSeg();
            if (!first || !last) return;
            var selRange = document.createRange();
            selRange.setStart(first, 0);
            selRange.setEnd(last, last.childNodes.length);
            var sel = window.getSelection();
            if (sel) { sel.removeAllRanges(); sel.addRange(selRange); }
            return;
        }
        if (e.key === 'ArrowRight' && idx < segs.length - 1 && isAtEnd(activeSeg)) {
            e.preventDefault(); segs[idx + 1].focus(); placeCursorAtStart(segs[idx + 1]); return;
        }
        if (e.key === 'ArrowLeft' && idx > 0 && isAtStart(activeSeg)) {
            e.preventDefault(); segs[idx - 1].focus(); placeCursorAtEnd(segs[idx - 1]); return;
        }

        // Backspace at start of a non-first seg removes the preceding pill
        if (e.key === 'Backspace' && idx > 0 && isAtStart(activeSeg)) {
            var prevPill = activeSeg.previousElementSibling;
            if (prevPill && prevPill.dataset && prevPill.dataset.pill) {
                e.preventDefault(); removePillFromState(prevPill); return;
            }
        }
    });

    textOuter.addEventListener('focusout', function() { setTimeout(hideAc, 150); });

    // --- Input event (delegated) ---

    textOuter.addEventListener('input', function(e) {
        if (!e.target.classList.contains('todo-text-seg')) return;
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) { updateAc(); updateEmptyClass(); return; }
        var range = sel.getRangeAt(0);
        var tn = range.startContainer, pos = range.startOffset;

        if (tn.nodeType === Node.TEXT_NODE && tn.parentNode === e.target) {
            var text = tn.textContent;
            var before = text.slice(0, pos);
            var lastChar = before.slice(-1);

            if (lastChar === '^' || lastChar === '*' || lastChar === '~') {
                tn.textContent = text.slice(0, pos - 1) + text.slice(pos);
                range.setStart(tn, pos - 1); range.collapse(true);
                sel.removeAllRanges(); sel.addRange(range);
                hideAc();
                if (lastChar === '^') openDatePillPicker();
                else if (lastChar === '*') openRecurrencePillPicker();
                else openNotePillPicker();
                updateEmptyClass();
                return;
            }

            var m = before.replace(/\u00a0/g, ' ').match(/#(\S+) $/);
            if (m) {
                var tag = m[1], removeLen = m[0].length;
                var beforeText = text.slice(0, pos - removeLen).replace(/\s+$/, ' ');
                tn.textContent = beforeText + ' ' + text.slice(pos);
                var newPos = beforeText.length + 1;
                range.setStart(tn, newPos); range.collapse(true);
                sel.removeAllRanges(); sel.addRange(range);
                hideAc(); addTag(tag); updateEmptyClass();
                return;
            }
        }

        updateAc();
        updateEmptyClass();
    });

    // Strip rich formatting on paste
    textOuter.addEventListener('paste', function(e) {
        if (!e.target.classList.contains('todo-text-seg')) return;
        e.preventDefault();
        var text = (e.clipboardData || window.clipboardData).getData('text/plain');
        if (!text) return;
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) return;
        var range = sel.getRangeAt(0);
        range.deleteContents();
        var inserted = document.createTextNode(text);
        range.insertNode(inserted);
        range.setStartAfter(inserted); range.collapse(true);
        sel.removeAllRanges(); sel.addRange(range);
        e.target.dispatchEvent(new Event('input', {bubbles: true}));
    });

    // --- Edit mode ---

    function enterEditMode(id, text, tagList, dueDate, recurrence, editUrl, note) {
        savedTags = tags.slice();
        savedDateISO = dateISO;
        savedRecLabel = recLabel;
        savedNoteText = noteText;
        editingId = id;
        tags = tagList.slice();
        dateISO = dueDate || null;
        dateLabel = null;
        recLabel = recurrence || null;
        noteText = note || '';
        _placeholder = 'Edit todo\u2026';
        renderAllPills(text || '');
        form.setAttribute('hx-post', editUrl);
        htmx.process(form);
        container.classList.add('todo-tag-input--editing');
        var first = getFirstSeg();
        if (first) { first.focus(); setTimeout(function() { placeCursorAtEnd(first); }, 0); }
        renderQuickPick();
    }

    function exitEditMode() {
        editingId = null;
        tags = savedTags !== null ? savedTags : []; savedTags = null;
        dateISO = savedDateISO; dateLabel = null; savedDateISO = null;
        recLabel = savedRecLabel; savedRecLabel = null;
        noteText = savedNoteText !== null ? savedNoteText : ''; savedNoteText = null;
        _placeholder = 'New todo\u2026';
        renderAllPills('');
        renderQuickPick();
        form.setAttribute('hx-post', addUrl);
        htmx.process(form);
        container.classList.remove('todo-tag-input--editing');
    }

    document.addEventListener('todoEditStart', function(e) {
        var d = e.detail;
        enterEditMode(d.id, d.text, d.tags, d.dueDate, d.recurrence, d.editUrl, d.note || '');
    });

    // --- Form submission ---

    var _pendingText = null;

    function buildCompositeText() {
        var rawText = getPlainText();
        var typedTags = (rawText.match(/#\S+/g) || []).map(function(t) { return t.slice(1); });
        var allTags = tags.slice();
        typedTags.forEach(function(t) { if (allTags.indexOf(t) === -1) allTags.push(t); });
        var cleanText = rawText.replace(/#\S+/g, '').replace(/\s+/g, ' ').trim();
        var parts = [cleanText].concat(allTags.map(function(t) { return '#' + t; }));
        if (dateISO) parts.push('^' + dateISO);
        if (recLabel) parts.push('*' + recLabel);
        if (noteText) parts.push('~' + noteText);
        return parts.join(' ').trim();
    }

    form.addEventListener('submit', function() {
        hideAc();
        _pendingText = buildCompositeText();
        if (editingId) {
            tags = savedTags !== null ? savedTags : [];
            savedTags = null; savedDateISO = null; savedRecLabel = null; savedNoteText = null;
            editingId = null;
            container.classList.remove('todo-tag-input--editing');
            _placeholder = 'New todo\u2026';
        }
        sessionStorage.setItem('todo-tags', JSON.stringify(tags));
        dateISO = null; dateLabel = null; recLabel = null; noteText = '';
        renderAllPills('');
    }, true);

    form.addEventListener('htmx:configRequest', function(e) {
        if (_pendingText !== null) { e.detail.parameters['text'] = _pendingText; _pendingText = null; }
    });

    document.body.addEventListener('showAddTodoError', function(e) {
        var raw = e.detail.input || '';
        var parsed = parseTagsFromRaw(raw);
        parsed.tags.forEach(function(t) { if (tags.indexOf(t) === -1) tags.push(t); });
        renderAllPills(parsed.text || '');
        renderQuickPick();
        focusFirstSeg();
    }, true);

    renderAllPills('');
    renderQuickPick();
}

// Show error toast when todo text is empty (only tags entered)
document.body.addEventListener('showAddTodoError', function(e) {
    var existing = document.getElementById('error-toast');
    if (existing) existing.remove();

    var toast = document.createElement('div');
    toast.id = 'error-toast';
    toast.style.cssText = 'position:fixed;bottom:1.5rem;left:1.5rem;z-index:9999;background:#dc2626;color:#fff;padding:0.875rem 1.25rem;border-radius:0.75rem;box-shadow:0 8px 32px rgba(0,0,0,0.45);pointer-events:none;font-weight:600;';
    toast.textContent = 'A todo needs text, not just tags.';
    document.body.appendChild(toast);
    setTimeout(function() { toast.remove(); }, 5000);
});

var _undoTimer = null;

// Show undo toast when server fires showUndoToast HX-Trigger event
document.body.addEventListener('showUndoToast', function(e) {
    var existing = document.getElementById('undo-toast');
    if (existing) existing.remove();
    clearTimeout(_undoTimer);

    var toast = document.createElement('div');
    toast.id = 'undo-toast';
    toast.dataset.todoIds = e.detail.ids;
    toast.dataset.prevStatus = e.detail.prevStatus;
    toast.dataset.label = e.detail.label || '';
    toast.className = 'undo-toast';
    toast.style.cssText = 'background:#fef3c7;color:#78350f;border:1px solid #f59e0b;padding:0.875rem 1.25rem;border-radius:0.75rem;box-shadow:0 8px 32px rgba(0,0,0,0.2);cursor:pointer;font-weight:600;';
    toast.textContent = (e.detail.label || 'Item') + ' ' + (e.detail.action || 'completed') + '. (Undo)';

    toast.addEventListener('click', function() {
        document.dispatchEvent(new KeyboardEvent('keydown', {key: 'u', bubbles: true}));
    });

    document.body.appendChild(toast);
    _undoTimer = setTimeout(function() { toast.remove(); }, 7000);
});

document.body.addEventListener('showUndoConfirm', function(e) {
    var toast = document.getElementById('undo-toast');
    if (!toast) return;
    var label = e.detail.label || 'Item';
    toast.textContent = label + ' uncompleted. UNDO OK.';
    toast.style.background = '#dcfce7';
    toast.style.color = '#14532d';
    toast.style.borderColor = '#16a34a';
    toast.style.cursor = 'default';
    _undoTimer = setTimeout(function() { toast.remove(); }, 2500);
});

var _hoveredTodoItem = null;
document.addEventListener('mouseover', function(e) {
    _hoveredTodoItem = e.target.closest('.todo-item') || _hoveredTodoItem;
});
document.addEventListener('mouseleave', function(e) {
    if (e.target.closest && e.target.closest('.todo-item') === _hoveredTodoItem) _hoveredTodoItem = null;
}, true);

document.addEventListener('keydown', function(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.contentEditable === 'true') return;

    // 'r' key: restore checked items on the done list, or hovered item as fallback
    if (e.key === 'r') {
        var doneList = document.getElementById('done-list');
        if (!doneList) return;
        var boxes = Array.from(document.querySelectorAll('input.todo-checkbox:checked'));
        var ids;
        if (boxes.length > 0) {
            ids = boxes.map(function(b) { return b.dataset.id; }).join(',');
        } else if (_hoveredTodoItem) {
            var hovered = _hoveredTodoItem.querySelector('.todo-checkbox');
            if (!hovered) return;
            ids = hovered.dataset.id;
        } else {
            return;
        }
        e.preventDefault();
        htmx.ajax('POST', doneList.dataset.batchActivateUrl,
                  {target: doneList, swap: 'innerHTML', values: {todo_ids: ids}});
        return;
    }

    if (e.key === 'e' && _hoveredTodoItem) {
        e.preventDefault();
        var li = _hoveredTodoItem;
        document.dispatchEvent(new CustomEvent('todoEditStart', {detail: {
            id: li.id.replace('todo-', ''),
            text: li.dataset.todoText || '',
            note: li.dataset.todoNote || '',
            tags: (li.dataset.todoTags || '').split(',').filter(Boolean),
            dueDate: li.dataset.dueDate || null,
            recurrence: li.dataset.recurrence || null,
            editUrl: li.dataset.editUrl || ''
        }}));
        return;
    }

    var list = document.getElementById('todo-list');
    if (!list) return;

    var key = e.key;

    function _targetIds() {
        var boxes = Array.from(document.querySelectorAll('input.todo-checkbox:checked'));
        if (boxes.length > 0) {
            return boxes.map(function(b) { return b.dataset.id; }).join(',');
        }
        if (_hoveredTodoItem) {
            var hovered = _hoveredTodoItem.querySelector('.todo-checkbox');
            return hovered ? hovered.dataset.id : null;
        }
        return null;
    }

    if (key === 'c' || key === 'h' || key === 'p') {
        var ids = _targetIds();
        if (!ids) return;
        e.preventDefault();
        var url = key === 'c' ? list.dataset.doneUrl
                : key === 'h' ? list.dataset.holdUrl
                : list.dataset.postponeUrl;
        htmx.ajax('POST', url, {target: list, swap: 'innerHTML', values: {todo_ids: ids}});
        return;
    }

    if (key === 'P' && e.shiftKey) {
        var ids2 = _targetIds();
        if (!ids2) return;
        e.preventDefault();
        openPostponePicker(_hoveredTodoItem, ids2);
        return;
    }

    if (key === 'd' && _hoveredTodoItem) {
        e.preventDefault();
        openSetDuePicker(_hoveredTodoItem);
        return;
    }

    if (key === 'f' && _hoveredTodoItem) {
        e.preventDefault();
        openSetRecurrencePicker(_hoveredTodoItem);
        return;
    }

    if (key === 'u') {
        var toast = document.getElementById('undo-toast');
        if (!toast) return;
        e.preventDefault();
        clearTimeout(_undoTimer);
        htmx.ajax('POST', list.dataset.undoUrl,
                  {target: list, swap: 'innerHTML',
                   values: {todo_ids: toast.dataset.todoIds, prev_status: toast.dataset.prevStatus}});
    }
});

// --- Unified date picker ----------------------------------------------------
//
// A single popover used by the ^-pill flow, the d-key flow, and Shift+P. It
// shows a row of quick chips (today, tomorrow, the next three weekdays, +1
// week, "no date"), a free-text field with live parser preview, and a month
// calendar grid. The caller passes a mode + onCommit callback.
//
//   mode: 'pill'    \u2192 onCommit(iso, label) \u2014 caller inserts a pill
//         'set-due' \u2192 caller does whatever it wants on commit (we just call
//                     onCommit; helpers below POST to set_due_date)
//
// Always returns ISO ('YYYY-MM-DD') or null for "no date".

function _isoDate(d) {
    return d.getFullYear() + '-'
         + String(d.getMonth() + 1).padStart(2, '0') + '-'
         + String(d.getDate()).padStart(2, '0');
}

function _addDays(d, n) {
    var x = new Date(d);
    x.setDate(x.getDate() + n);
    return x;
}

function _quickOptions() {
    var t = new Date();
    var weekdayShort = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    var opts = [
        {label: 'Today', iso: _isoDate(t)},
        {label: 'Tomorrow', iso: _isoDate(_addDays(t, 1))},
    ];
    for (var i = 2; i <= 4; i++) {
        var d = _addDays(t, i);
        opts.push({label: weekdayShort[d.getDay()], iso: _isoDate(d)});
    }
    opts.push({label: '+1 week', iso: _isoDate(_addDays(t, 7))});
    opts.push({label: 'No date', iso: null});
    return opts;
}

function openPicker(opts) {
    closePopovers();
    var pop = document.createElement('div');
    pop.className = 'todo-popover';
    pop.dataset.role = opts.role || 'date-picker';

    if (opts.title) {
        var h = document.createElement('div');
        h.style.cssText = 'font-size:0.75rem;font-weight:600;color:var(--bs-secondary-color);margin-bottom:0.35rem;';
        h.textContent = opts.title;
        pop.appendChild(h);
    }

    // --- Quick chips row ---
    var chips = document.createElement('div');
    chips.className = 'todo-popover-actions';
    chips.style.marginTop = '0';
    pop.appendChild(chips);

    // --- Custom text input + live preview ---
    var input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'tomorrow / next wed / 2026-05-12 \u2026';
    input.value = opts.initialISO || '';
    pop.appendChild(input);

    var preview = document.createElement('div');
    preview.className = 'todo-popover-preview';
    pop.appendChild(preview);

    // --- Calendar ---
    var cal = document.createElement('div');
    pop.appendChild(cal);

    // --- Footer actions ---
    var footer = document.createElement('div');
    footer.className = 'todo-popover-actions';
    var setBtn = document.createElement('button');
    setBtn.type = 'button';
    setBtn.textContent = opts.commitLabel || 'Set';
    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = 'Cancel';
    footer.appendChild(setBtn);
    footer.appendChild(cancelBtn);
    pop.appendChild(footer);

    anchorPopover(pop, opts.anchorEl);

    // --- State ---
    var pendingISO = opts.initialISO || null;
    var pendingMonth = pendingISO
        ? new Date(pendingISO + 'T00:00:00')
        : new Date();
    pendingMonth.setDate(1);

    function commit(iso) {
        if (typeof opts.onCommit === 'function') opts.onCommit(iso);
        closePopovers();
    }

    function cancel() {
        if (typeof opts.onCancel === 'function') opts.onCancel();
        closePopovers();
    }

    // --- Render quick chips ---
    _quickOptions().forEach(function(opt) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = opt.label;
        btn.addEventListener('click', function() { commit(opt.iso); });
        chips.appendChild(btn);
    });

    // --- Render calendar ---
    function renderCalendar() {
        cal.innerHTML = '';

        var nav = document.createElement('div');
        nav.style.cssText = 'display:flex;justify-content:space-between;align-items:center;font-size:0.75rem;font-weight:600;color:var(--bs-secondary-color);margin:0.25rem 0;';
        var prev = document.createElement('button');
        prev.type = 'button';
        prev.textContent = '\u2039';
        prev.style.cssText = 'background:none;border:none;cursor:pointer;font-size:1rem;color:inherit;padding:0 0.5rem;';
        prev.addEventListener('click', function() {
            pendingMonth.setMonth(pendingMonth.getMonth() - 1);
            renderCalendar();
        });
        var next = document.createElement('button');
        next.type = 'button';
        next.textContent = '\u203a';
        next.style.cssText = prev.style.cssText;
        next.addEventListener('click', function() {
            pendingMonth.setMonth(pendingMonth.getMonth() + 1);
            renderCalendar();
        });
        var navLabel = document.createElement('span');
        navLabel.textContent = pendingMonth.toLocaleDateString(undefined, {month: 'long', year: 'numeric'});
        nav.appendChild(prev);
        nav.appendChild(navLabel);
        nav.appendChild(next);
        cal.appendChild(nav);

        var grid = document.createElement('div');
        grid.className = 'todo-mini-cal';
        ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].forEach(function(d) {
            var hCell = document.createElement('div');
            hCell.className = 'todo-mini-cal-cell todo-mini-cal-header';
            hCell.textContent = d;
            grid.appendChild(hCell);
        });

        var first = new Date(pendingMonth);
        first.setDate(1);
        var startWeekday = (first.getDay() + 6) % 7; // Mon=0
        var daysInMonth = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
        var todayISO = _isoDate(new Date());

        for (var i = 0; i < startWeekday; i++) {
            var blank = document.createElement('div');
            blank.className = 'todo-mini-cal-cell muted';
            grid.appendChild(blank);
        }
        for (var d = 1; d <= daysInMonth; d++) {
            var cell = document.createElement('div');
            cell.className = 'todo-mini-cal-cell';
            cell.textContent = d;
            var iso = _isoDate(new Date(first.getFullYear(), first.getMonth(), d));
            if (iso === todayISO) cell.classList.add('today');
            if (iso === pendingISO) cell.classList.add('selected');
            cell.addEventListener('click', (function(iso) { return function() { commit(iso); }; }(iso)));
            grid.appendChild(cell);
        }
        cal.appendChild(grid);
    }

    // --- Live preview from custom input ---
    var previewTimer = null;
    function updatePreview() {
        clearTimeout(previewTimer);
        var q = input.value.trim();
        if (!q) {
            preview.textContent = '';
            preview.classList.remove('todo-popover-preview--invalid');
            pendingISO = null;
            return;
        }
        previewTimer = setTimeout(function() {
            fetch('/todos/parse-date?q=' + encodeURIComponent(q))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.ok) {
                        pendingISO = data.date;
                        preview.textContent = '\u2192 ' + data.label + ' (' + data.date + ')';
                        preview.classList.remove('todo-popover-preview--invalid');
                        // Re-render calendar to month containing the new date
                        var newMonth = new Date(data.date + 'T00:00:00');
                        if (newMonth.getMonth() !== pendingMonth.getMonth()
                            || newMonth.getFullYear() !== pendingMonth.getFullYear()) {
                            pendingMonth = newMonth;
                            pendingMonth.setDate(1);
                        }
                        renderCalendar();
                    } else {
                        pendingISO = null;
                        preview.textContent = '? cannot parse';
                        preview.classList.add('todo-popover-preview--invalid');
                    }
                })
                .catch(function() {});
        }, 120);
    }

    input.addEventListener('input', updatePreview);
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); commit(pendingISO); }
        else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
    });
    setBtn.addEventListener('click', function() { commit(pendingISO); });
    cancelBtn.addEventListener('click', cancel);

    renderCalendar();
    if (opts.initialISO) updatePreview();
    setTimeout(function() { input.focus(); input.select(); }, 0);
    return pop;
}

// Simple note-text popover. opts: {anchorEl, initialNote, title, onCommit, onCancel}
function openNotePicker(opts) {
    closePopovers();
    var pop = document.createElement('div');
    pop.className = 'todo-popover todo-note-popover';
    pop.style.cssText = 'position:absolute;z-index:1060;background:#fff;border:1px solid #dee2e6;border-radius:.5rem;padding:1rem;box-shadow:0 4px 20px rgba(0,0,0,.15);width:18rem;';
    var safeInitial = (opts.initialNote || '').replace(/"/g, '&quot;');
    pop.innerHTML = '<label style="font-size:.85rem;font-weight:600;display:block;margin-bottom:.5rem">'
        + (opts.title || 'Note') + '</label>'
        + '<input type="text" class="form-control form-control-sm" placeholder="Note text\u2026" value="' + safeInitial + '"/>'
        + '<div class="d-flex gap-2 mt-2 justify-content-end">'
        + '<button type="button" class="btn btn-sm btn-link text-muted">Cancel</button>'
        + '<button type="button" class="btn btn-sm btn-dark">Set</button>'
        + '</div>';
    anchorPopover(pop, opts.anchorEl);
    var input = pop.querySelector('input');
    var setBtn = pop.querySelector('.btn-dark');
    var cancelBtn = pop.querySelector('.btn-link');
    function commit() {
        var val = input.value.trim();
        closePopovers();
        if (opts.onCommit) opts.onCommit(val);
    }
    function cancel() {
        closePopovers();
        if (opts.onCancel) opts.onCancel();
    }
    setBtn.addEventListener('click', commit);
    cancelBtn.addEventListener('click', cancel);
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); commit(); }
        if (e.key === 'Escape') { cancel(); }
    });
    setTimeout(function() { input.focus(); input.select(); }, 0);
}

// Anchor a popover element below `anchorEl`. Removes any existing popovers first.
function anchorPopover(pop, anchorEl) {
    document.body.appendChild(pop);
    var rect = anchorEl ? anchorEl.getBoundingClientRect()
                        : {top: 100, left: 100, bottom: 100, right: 100};
    var top = window.scrollY + rect.bottom + 4;
    var left = window.scrollX + Math.min(rect.left, window.innerWidth - 320);
    pop.style.top = top + 'px';
    pop.style.left = Math.max(8, left) + 'px';
}

function closePopovers() {
    document.querySelectorAll('.todo-popover').forEach(function(el) { el.remove(); });
}

// Click-outside closes any open popover.
document.addEventListener('mousedown', function(e) {
    if (e.target.closest('.todo-popover')) return;
    if (e.target.closest('.todo-due')) return;
    if (e.target.closest('.todo-date-pill')) return;
    closePopovers();
});

// --- Helpers wrapping openPicker for specific contexts ---

function openSetDuePicker(itemEl) {
    var url = itemEl.dataset.setDueUrl;
    if (!url) return;
    var list = document.getElementById('todo-list');
    openPicker({
        anchorEl: itemEl,
        initialISO: itemEl.dataset.dueDate || null,
        title: 'Due date',
        onCommit: function(iso) {
            htmx.ajax('POST', url, {
                target: list || document.body, swap: list ? 'innerHTML' : 'none',
                values: {due_date: iso || ''}
            });
        }
    });
}

function openPostponePicker(itemEl, ids) {
    var list = document.getElementById('todo-list');
    if (!list) return;
    openPicker({
        anchorEl: itemEl,
        title: 'Postpone\u2026',
        role: 'postpone-palette',
        onCommit: function(iso) {
            htmx.ajax('POST', list.dataset.postponeUrl, {
                target: list, swap: 'innerHTML',
                values: {todo_ids: ids, due_date: iso || ''}
            });
        }
    });
}

// Click on the due-date chip opens the set-due picker for that row.
document.addEventListener('click', function(e) {
    var chip = e.target.closest('.todo-due');
    if (!chip) return;
    var item = chip.closest('.todo-item');
    if (!item || !item.dataset.setDueUrl) return;
    e.stopPropagation();
    openSetDuePicker(item);
});

// --- Recurrence picker ----------------------------------------------------
//
// Mirrors openPicker but for repetition rules. Calls /todos/parse-recurrence
// for live preview. Quick chips cover the common cases per the spec; the
// free-text field accepts anything parse_recurrence understands.

var _RECURRENCE_CHIPS = [
    'every day', 'every week', 'every month', 'every year',
    'after a day', 'after a week', 'after a month', 'after a year',
];

function openRecurrencePicker(opts) {
    closePopovers();
    var pop = document.createElement('div');
    pop.className = 'todo-popover';
    pop.dataset.role = opts.role || 'recurrence-picker';

    if (opts.title) {
        var h = document.createElement('div');
        h.style.cssText = 'font-size:0.75rem;font-weight:600;color:var(--bs-secondary-color);margin-bottom:0.35rem;';
        h.textContent = opts.title;
        pop.appendChild(h);
    }

    var chips = document.createElement('div');
    chips.className = 'todo-popover-actions';
    chips.style.marginTop = '0';
    pop.appendChild(chips);

    var input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'every wednesday / after 10 days / every 15th \u2026';
    input.value = opts.initialLabel || '';
    pop.appendChild(input);

    var preview = document.createElement('div');
    preview.className = 'todo-popover-preview';
    pop.appendChild(preview);

    var footer = document.createElement('div');
    footer.className = 'todo-popover-actions';
    var setBtn = document.createElement('button');
    setBtn.type = 'button';
    setBtn.textContent = opts.commitLabel || 'Set';
    var clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.textContent = 'No repeat';
    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = 'Cancel';
    footer.appendChild(setBtn);
    footer.appendChild(clearBtn);
    footer.appendChild(cancelBtn);
    pop.appendChild(footer);

    anchorPopover(pop, opts.anchorEl);

    var pendingLabel = opts.initialLabel || null;

    function commit(label) {
        if (typeof opts.onCommit === 'function') opts.onCommit(label || null);
        closePopovers();
    }
    function cancel() {
        if (typeof opts.onCancel === 'function') opts.onCancel();
        closePopovers();
    }

    _RECURRENCE_CHIPS.forEach(function(label) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = label;
        btn.addEventListener('click', function() { commit(label); });
        chips.appendChild(btn);
    });

    var previewTimer = null;
    function updatePreview() {
        clearTimeout(previewTimer);
        var q = input.value.trim();
        if (!q) {
            preview.textContent = '';
            preview.classList.remove('todo-popover-preview--invalid');
            pendingLabel = null;
            return;
        }
        previewTimer = setTimeout(function() {
            fetch('/todos/parse-recurrence?q=' + encodeURIComponent(q))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.ok) {
                        pendingLabel = data.label;
                        preview.textContent = '\u21bb ' + data.label;
                        preview.classList.remove('todo-popover-preview--invalid');
                    } else {
                        pendingLabel = null;
                        preview.textContent = '? cannot parse';
                        preview.classList.add('todo-popover-preview--invalid');
                    }
                })
                .catch(function() {});
        }, 120);
    }
    input.addEventListener('input', updatePreview);
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); commit(pendingLabel); }
        else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
    });
    setBtn.addEventListener('click', function() { commit(pendingLabel); });
    clearBtn.addEventListener('click', function() { commit(null); });
    cancelBtn.addEventListener('click', cancel);

    if (opts.initialLabel) updatePreview();
    setTimeout(function() { input.focus(); input.select(); }, 0);
    return pop;
}

function openSetRecurrencePicker(itemEl) {
    var url = itemEl.dataset.setRecUrl;
    if (!url) return;
    var list = document.getElementById('todo-list');
    openRecurrencePicker({
        anchorEl: itemEl,
        initialLabel: itemEl.dataset.recurrence || null,
        title: 'Repeat',
        onCommit: function(label) {
            htmx.ajax('POST', url, {
                target: list || document.body,
                swap: list ? 'innerHTML' : 'none',
                values: {recurrence: label || ''}
            });
        }
    });
}

// --- Repetition history panel ---
function openHistoryPanel(itemEl) {
    var url = itemEl.dataset.historyUrl;
    if (!url) return;
    closePopovers();
    closeHistoryPanel();
    fetch(url, {headers: {'Accept': 'text/html'}})
        .then(function(r) { return r.text(); })
        .then(function(html) {
            var wrap = document.createElement('div');
            wrap.id = 'todo-history-wrap';
            wrap.innerHTML = html;
            document.body.appendChild(wrap);
        });
}
function closeHistoryPanel() {
    var w = document.getElementById('todo-history-wrap');
    if (w) w.remove();
}
document.addEventListener('click', function(e) {
    if (e.target.closest('.todo-history-close')) {
        closeHistoryPanel();
        return;
    }
    var rec = e.target.closest('.todo-recurrence');
    if (rec) {
        var item = rec.closest('.todo-item');
        if (item && item.dataset.historyUrl) {
            e.stopPropagation();
            openHistoryPanel(item);
        }
    }
});

// --- Keyboard shortcut help overlay ---
// HTMX swaps body content frequently and removes any element previously
// appended to <body>. We therefore (a) keep `_helpOverlay` as a singleton we
// can re-attach on every load and (b) bind the keydown handler exactly once
// against `document`, which is never replaced.
var _helpOverlay = null;

function _kbdSection(title) {
    return '<p style="font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#94a3b8;margin:0 0 0.35rem;">' + title + '</p>';
}

function _kbdRow(key, desc) {
    return '<tr><td style="padding:0.25rem 0.75rem 0.25rem 0;white-space:nowrap;">'
         + '<kbd style="background:#f1f5f9;border:1px solid #cbd5e1;border-radius:0.25rem;padding:0.1rem 0.4rem;font-family:monospace;font-size:0.8rem;">'
         + key + '</kbd></td>'
         + '<td style="padding:0.25rem 0;color:#374151;">' + desc + '</td></tr>';
}

function ensureHelpOverlay() {
    if (_helpOverlay && document.body.contains(_helpOverlay)) return _helpOverlay;
    _helpOverlay = document.createElement('div');
    _helpOverlay.id = 'kbd-help-overlay';
    _helpOverlay.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:9999;align-items:center;justify-content:center;';
    _helpOverlay.innerHTML = [
        '<div style="background:#fff;border-radius:0.75rem;padding:1.5rem 2rem;max-width:28rem;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.2);max-height:90vh;overflow:auto;">',
        '<h2 style="font-size:0.9rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;margin:0 0 1rem;">Keyboard shortcuts</h2>',

        _kbdSection('Everywhere'),
        '<table style="width:100%;border-collapse:collapse;font-size:0.875rem;margin-bottom:1rem;"><tbody>',
        _kbdRow('?', 'Show this help'),
        _kbdRow('Esc', 'Cancel / close'),
        '</tbody></table>',

        _kbdSection('Todo list'),
        '<table style="width:100%;border-collapse:collapse;font-size:0.875rem;margin-bottom:1rem;"><tbody>',
        _kbdRow('click', 'Select / deselect item'),
        _kbdRow('e', 'Edit hovered item'),
        _kbdRow('c', 'Mark hovered / selected done'),
        _kbdRow('h', 'Put hovered / selected on hold'),
        _kbdRow('d', 'Set / change due date (hovered)'),
        _kbdRow('f', 'Set / change repetition rule (hovered)'),
        _kbdRow('p', 'Postpone hovered / selected by 1 day'),
        _kbdRow('Shift+P', 'Postpone\u2026 (chip palette + calendar)'),
        _kbdRow('r', 'Open the protocol palette \u2014 start a run'),
        _kbdRow('u', 'Undo last action'),
        _kbdRow('click \u21bb', 'Show repetition history for this item'),
        '</tbody></table>',

        _kbdSection('Protocol run'),
        '<table style="width:100%;border-collapse:collapse;font-size:0.875rem;margin-bottom:1rem;"><tbody>',
        _kbdRow('j / \u2193', 'Next item'),
        _kbdRow('k / \u2191', 'Previous item'),
        _kbdRow('c', 'Mark current done \u2014 nothing to do'),
        _kbdRow('t', 'Send current to the todo list'),
        _kbdRow('e', 'Edit current item before sending'),
        _kbdRow('Esc', 'Back to the todo list'),
        _kbdRow('swipe \u2192', 'Same as <kbd>c</kbd> (done)'),
        _kbdRow('swipe \u2190', 'Same as <kbd>t</kbd> (send to todo)'),
        '</tbody></table>',

        _kbdSection('Adding / editing a todo'),
        '<table style="width:100%;border-collapse:collapse;font-size:0.875rem;margin-bottom:1rem;"><tbody>',
        _kbdRow('#tag', 'Attach a tag (single word)'),
        _kbdRow('^', 'Open the date picker \u2014 commits as a pill'),
        _kbdRow('*', 'Open the repetition picker \u2014 commits as a pill'),
        '</tbody></table>',

        _kbdSection('Done list'),
        '<table style="width:100%;border-collapse:collapse;font-size:0.875rem;margin-bottom:0.25rem;"><tbody>',
        _kbdRow('click', 'Select / deselect item'),
        _kbdRow('r', 'Restore selected items'),
        '</tbody></table>',

        '</div>'
    ].join('');
    document.body.appendChild(_helpOverlay);
    _helpOverlay.addEventListener('click', function(e) {
        if (e.target === _helpOverlay) hideHelp();
    });
    return _helpOverlay;
}

function showHelp() {
    var o = ensureHelpOverlay();
    o.style.display = 'flex';
}

function hideHelp() {
    if (_helpOverlay) _helpOverlay.style.display = 'none';
}

// Bound once on document \u2014 never replaced by HTMX. `?` should fire even when
// the user is mid-typing in the add-todo input: opening help shouldn't depend
// on what's focused.
document.addEventListener('keydown', function(e) {
    if (e.key === '?') { e.preventDefault(); showHelp(); return; }
    if (e.key === 'Escape' && _helpOverlay && _helpOverlay.style.display === 'flex') {
        e.preventDefault();
        hideHelp();
    }
});

// --- Protocol run page interactions ----------------------------------------
//
// Run-item actions (done / send-to-todo / edit) are dispatched via delegation
// on .protocol-run-action buttons inside #protocol-run. Each .protocol-run-item
// carries data-done-url / data-send-url / data-edit-url to keep the JS
// parameter-free.

(function _wireRunActions() {
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('.protocol-run-action');
        if (!btn) return;
        var item = btn.closest('.protocol-run-item');
        if (!item) return;
        var action = btn.dataset.action;
        if (action === 'edit') return runItemEditInline(item);
        var url = action === 'done' ? item.dataset.doneUrl : item.dataset.sendUrl;
        var run = document.getElementById('protocol-run');
        if (!url || !run) return;
        e.preventDefault();
        htmx.ajax('POST', url, {target: run, swap: 'innerHTML'});
    });
}());

function runItemEditInline(itemEl) {
    var textSpan = itemEl.querySelector('.flex-grow-1 > span');
    if (!textSpan) return;
    var existing = textSpan.textContent.trim();
    var input = document.createElement('input');
    input.type = 'text';
    input.value = existing;
    input.className = 'form-control form-control-sm';
    input.style.maxWidth = '20rem';
    textSpan.replaceWith(input);
    input.focus();
    input.select();
    function commit() {
        var run = document.getElementById('protocol-run');
        var url = itemEl.dataset.editUrl;
        if (!url || !run) return;
        htmx.ajax('POST', url, {target: run, swap: 'innerHTML', values: {text: input.value}});
    }
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); commit(); }
        else if (e.key === 'Escape') { input.replaceWith(textSpan); }
    });
    input.addEventListener('blur', commit);
}

// --- Run-item navigation + hotkeys ---
var _runCurrentIdx = 0;

function _runItems() {
    return Array.from(document.querySelectorAll('.protocol-run-item'));
}
function _runHighlight() {
    var items = _runItems();
    items.forEach(function(el, i) {
        el.classList.toggle('is-current', i === _runCurrentIdx);
    });
    var current = items[_runCurrentIdx];
    if (current) current.scrollIntoView({block: 'nearest', behavior: 'smooth'});
}
function _runMove(delta) {
    var items = _runItems();
    if (!items.length) return;
    _runCurrentIdx = Math.max(0, Math.min(items.length - 1, _runCurrentIdx + delta));
    _runHighlight();
}
function _runFire(action) {
    var items = _runItems();
    var current = items[_runCurrentIdx];
    if (!current) return;
    var btn = current.querySelector('.protocol-run-action[data-action="' + action + '"]');
    if (btn) btn.click();
}

document.addEventListener('keydown', function(e) {
    if (!document.getElementById('protocol-run')) return;
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.contentEditable === 'true') return;
    if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); _runMove(1); }
    else if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); _runMove(-1); }
    else if (e.key === 'c') { e.preventDefault(); _runFire('done'); }
    else if (e.key === 't') { e.preventDefault(); _runFire('send'); }
    else if (e.key === 'e') { e.preventDefault(); _runFire('edit'); }
    else if (e.key === 'Escape') {
        e.preventDefault();
        var run = document.getElementById('protocol-run');
        if (run && run.dataset.todoRoute) location.href = run.dataset.todoRoute;
    }
});

// --- Swipe for run items ---
var _runSwipeState = new WeakMap();
document.addEventListener('touchstart', function(e) {
    var item = e.target.closest('.protocol-run-item');
    if (!item) return;
    var inner = item.querySelector('.card-body');
    if (!inner) return;
    inner.style.transition = 'none';
    _runSwipeState.set(item, {startX: e.touches[0].clientX, dx: 0});
}, {passive: true});
document.addEventListener('touchmove', function(e) {
    var item = e.target.closest('.protocol-run-item');
    if (!item) return;
    var s = _runSwipeState.get(item);
    if (!s) return;
    var inner = item.querySelector('.card-body');
    if (!inner) return;
    s.dx = e.touches[0].clientX - s.startX;
    inner.style.transform = 'translateX(' + Math.max(-150, Math.min(150, s.dx)) + 'px)';
    item.dataset.swipeDir = s.dx > 0 ? 'right' : (s.dx < 0 ? 'left' : '');
}, {passive: true});
document.addEventListener('touchend', function(e) {
    var item = e.target.closest('.protocol-run-item');
    if (!item) return;
    var s = _runSwipeState.get(item);
    if (!s) return;
    _runSwipeState.delete(item);
    var inner = item.querySelector('.card-body');
    if (!inner) return;
    inner.style.transition = 'transform 0.2s ease';
    var dx = s.dx;
    if (dx >= 80) {
        inner.style.transform = 'translateX(100vw)';
        var btn = item.querySelector('.protocol-run-action[data-action="done"]');
        if (btn) btn.click();
    } else if (dx <= -80) {
        inner.style.transform = 'translateX(-100vw)';
        var sendBtn = item.querySelector('.protocol-run-action[data-action="send"]');
        if (sendBtn) sendBtn.click();
    } else {
        inner.style.transform = 'translateX(0)';
        delete item.dataset.swipeDir;
    }
});

// --- Protocol palette (r key on /todos) ---
var _palette = null;

function openProtocolPalette() {
    if (_palette) return;
    _palette = document.createElement('div');
    _palette.className = 'protocol-palette';
    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'protocol-palette-input';
    input.placeholder = 'Start a protocol \u2014 type to filter';
    var list = document.createElement('ul');
    list.className = 'protocol-palette-list';
    _palette.appendChild(input);
    _palette.appendChild(list);
    document.body.appendChild(_palette);
    input.focus();

    var protocols = [];
    var selected = 0;

    function render(filter) {
        list.innerHTML = '';
        var q = filter.trim().toLowerCase();
        var matches = q
            ? protocols.filter(function(p) { return p.title.toLowerCase().includes(q); })
            : protocols;
        if (!matches.length) {
            var empty = document.createElement('li');
            empty.className = 'protocol-palette-empty';
            empty.textContent = q ? 'No matches.' : 'No protocols defined yet.';
            list.appendChild(empty);
            return;
        }
        selected = Math.min(selected, matches.length - 1);
        matches.forEach(function(p, i) {
            var li = document.createElement('li');
            li.className = 'protocol-palette-item' + (i === selected ? ' is-selected' : '');
            li.textContent = p.title;
            li.dataset.id = p.id;
            li.addEventListener('click', function() { startRun(p.id); });
            list.appendChild(li);
        });
    }

    function startRun(id) {
        closeProtocolPalette();
        var form = document.createElement('form');
        form.method = 'post';
        form.action = '/protocols/' + id + '/start';
        document.body.appendChild(form);
        form.submit();
    }

    fetch('/protocols/palette.json')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            protocols = data;
            render('');
        });

    input.addEventListener('input', function() { selected = 0; render(input.value); });
    input.addEventListener('keydown', function(e) {
        var items = list.querySelectorAll('.protocol-palette-item');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selected = Math.min(items.length - 1, selected + 1);
            render(input.value);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selected = Math.max(0, selected - 1);
            render(input.value);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            var current = items[selected];
            if (current) startRun(current.dataset.id);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            closeProtocolPalette();
        }
    });
}

function closeProtocolPalette() {
    if (_palette) { _palette.remove(); _palette = null; }
}

document.addEventListener('mousedown', function(e) {
    if (!_palette) return;
    if (e.target.closest('.protocol-palette')) return;
    closeProtocolPalette();
});

document.addEventListener('keydown', function(e) {
    if (e.key !== 'r') return;
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.contentEditable === 'true') return;
    // Only on the todo list page (avoid interfering with the done page's r=restore)
    if (!document.getElementById('todo-list')) return;
    if (document.getElementById('done-list')) return; // /todos/done page
    e.preventDefault();
    openProtocolPalette();
});

// --- Protocol item editor (tag pills + note + HTMX partial save) -----------

var _protoTagCache = null;

function _fetchProtoTags(cb) {
    if (_protoTagCache !== null) { cb(_protoTagCache); return; }
    var fromPage = Array.from(document.querySelectorAll('.tag-group-header[data-tag]'))
        .map(function(el) { return el.dataset.tag; })
        .filter(function(t) { return t && t !== '__untagged__'; });
    if (fromPage.length) { _protoTagCache = fromPage; cb(fromPage); return; }
    var url = document.body.dataset.tagsUrl;
    if (!url) { cb([]); return; }
    fetch(url).then(function(r) { return r.json(); }).then(function(data) {
        _protoTagCache = data; cb(data);
    }).catch(function() { cb([]); });
}

function initProtocolItemInputs() {
    document.querySelectorAll('.proto-item-form').forEach(function(form) {
        if (form.dataset.protoInit) return;
        form.dataset.protoInit = '1';

        var hidden = form.querySelector('.proto-item-hidden');
        var wrap = form.querySelector('.proto-item-input-wrap');
        var textInput = form.querySelector('.proto-item-text');
        var quickPick = form.querySelector('.proto-item-quick-pick');
        var saveBtn = form.querySelector('.proto-item-save');
        if (!hidden || !textInput) return;

        var canonical = form.dataset.canonical || hidden.value;
        var tags = (canonical.match(/#(\S+)/g) || []).map(function(m) { return m.slice(1); });
        var noteMatch = canonical.match(/~(.+)$/);
        var noteText = noteMatch ? noteMatch[1].trim() : '';

        function buildHidden() {
            var t = textInput.value.trim();
            var tagStr = tags.map(function(tg) { return '#' + tg; }).join(' ');
            var parts = [t, tagStr].filter(Boolean);
            if (noteText) parts.push('~' + noteText);
            return parts.join(' ');
        }

        function syncSaveBtn() {
            if (!saveBtn) return;
            var changed = buildHidden() !== canonical;
            saveBtn.classList.toggle('d-none', !changed);
        }

        function updateHidden() {
            hidden.value = buildHidden();
            syncSaveBtn();
        }

        function renderNotePill() {
            wrap.querySelectorAll('.proto-note-pill').forEach(function(p) { p.remove(); });
            if (!noteText) return;
            var pill = document.createElement('span');
            pill.className = 'badge rounded-pill bg-info text-dark me-1 proto-note-pill';
            pill.style.cursor = 'pointer';
            pill.style.userSelect = 'none';
            pill.title = 'Click to edit note';
            var label = document.createTextNode('~ ' + noteText + ' ');
            var removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn-close btn-close-white';
            removeBtn.style.cssText = 'font-size:.55em; vertical-align:middle';
            removeBtn.setAttribute('aria-label', 'Remove note');
            removeBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                noteText = '';
                renderNotePill();
                updateHidden();
            });
            pill.addEventListener('click', function(e) {
                if (e.target === removeBtn) return;
                e.stopPropagation();
                openNotePicker({
                    anchorEl: wrap,
                    initialNote: noteText,
                    title: 'Note',
                    onCommit: function(text) {
                        noteText = text;
                        renderNotePill();
                        updateHidden();
                        textInput.focus();
                    },
                    onCancel: function() { textInput.focus(); }
                });
            });
            pill.appendChild(label);
            pill.appendChild(removeBtn);
            wrap.insertBefore(pill, textInput);
            updateHidden();
        }

        function renderPills() {
            wrap.querySelectorAll('.proto-tag-pill').forEach(function(p) { p.remove(); });
            tags.forEach(function(tag) {
                var pill = document.createElement('span');
                pill.className = 'badge rounded-pill bg-secondary me-1 proto-tag-pill';
                pill.style.cursor = 'default';
                pill.style.userSelect = 'none';
                var label = document.createTextNode('#' + tag + ' ');
                var removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.className = 'btn-close btn-close-white';
                removeBtn.style.cssText = 'font-size:.55em; vertical-align:middle';
                removeBtn.dataset.tag = tag;
                removeBtn.setAttribute('aria-label', 'Remove ' + tag);
                removeBtn.addEventListener('click', function(e) {
                    e.stopPropagation();
                    tags = tags.filter(function(t) { return t !== tag; });
                    renderPills();
                    renderQuickPick();
                });
                pill.appendChild(label);
                pill.appendChild(removeBtn);
                wrap.insertBefore(pill, textInput);
            });
            updateHidden();
        }

        function addTag(tag) {
            tag = tag.replace(/^#/, '');
            if (!tag || tags.indexOf(tag) !== -1) return;
            tags.push(tag);
            renderPills();
            renderQuickPick();
        }

        function renderQuickPick() {
            if (!quickPick) return;
            _fetchProtoTags(function(available) {
                var chips = available.filter(function(t) { return tags.indexOf(t) === -1; });
                if (!chips.length) { quickPick.style.display = 'none'; return; }
                quickPick.innerHTML = '';
                chips.forEach(function(tag) {
                    var chip = document.createElement('button');
                    chip.type = 'button';
                    chip.className = 'todo-quick-pick-chip';
                    chip.textContent = '#' + tag;
                    chip.addEventListener('click', function() { addTag(tag); textInput.focus(); });
                    quickPick.appendChild(chip);
                });
                quickPick.style.display = '';
            });
        }

        textInput.addEventListener('focus', function() { renderQuickPick(); });
        textInput.addEventListener('blur', function() {
            setTimeout(function() { if (quickPick) quickPick.style.display = 'none'; }, 200);
        });
        textInput.addEventListener('input', function() {
            var val = textInput.value;
            // ~ \u2192 open note picker
            var tildeIdx = val.indexOf('~');
            if (tildeIdx !== -1) {
                textInput.value = val.slice(0, tildeIdx) + val.slice(tildeIdx + 1);
                openNotePicker({
                    anchorEl: wrap,
                    initialNote: noteText,
                    title: 'Note',
                    onCommit: function(text) {
                        noteText = text;
                        renderNotePill();
                        updateHidden();
                        textInput.focus();
                    },
                    onCancel: function() { textInput.focus(); }
                });
                return;
            }
            var m = val.match(/(^|[\s\S]*[\s])#(\S+)\s$/);
            if (m && m[2]) {
                addTag(m[2]);
                textInput.value = (m[1] || '').trimEnd();
            } else {
                updateHidden();
            }
        });

        renderPills();
        renderNotePill();
    });
}

function deleteProtocolItem(btn) {
    var li = btn.closest('li');
    if (!li) return;
    var url = btn.dataset.deleteUrl;
    var saved = li.outerHTML;
    var placeholder = document.createElement('li');
    placeholder.className = 'card mb-1';
    placeholder.innerHTML = '<div class="card-body py-1 px-3 d-flex align-items-center gap-2">'
        + '<span class="text-muted small">Item deleted.</span>'
        + '<button type="button" class="btn btn-link btn-sm p-0">Undo</button>'
        + '</div>';
    placeholder._deleteTimer = setTimeout(function() {
        fetch(url, {method: 'POST'}).then(function(r) {
            if (!r.ok) {
                placeholder.insertAdjacentHTML('beforebegin', saved);
                placeholder.remove();
            } else {
                placeholder.remove();
            }
        });
    }, 5000);
    placeholder.querySelector('button').addEventListener('click', function() {
        clearTimeout(placeholder._deleteTimer);
        placeholder.insertAdjacentHTML('beforebegin', saved);
        placeholder.remove();
        initProtocolItemInputs();
    });
    li.replaceWith(placeholder);
}

htmx.onLoad(function(content) {
    ensureHelpOverlay();
    initSortables(content);
    initTodoSwipe(content);
    initTagInput();
    initProtocolItemInputs();
    if (document.getElementById('protocol-run')) _runHighlight();
});
ensureHelpOverlay();
initSortables(document);
initTodoSwipe(document);
initTagInput();
initProtocolItemInputs();
if (document.getElementById('protocol-run')) _runHighlight();
