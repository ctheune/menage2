// composite-input.js — unified pill-based text input component.
// Requires openPicker, openRecurrencePicker, openNotePicker, closePopovers (menage.js).

var _ciJsonCache = {};

function _ciFetchJSON(url, cb) {
    if (!url) { cb([]); return; }
    if (_ciJsonCache[url]) { cb(_ciJsonCache[url]); return; }
    fetch(url)
        .then(function(r) { return r.json(); })
        .then(function(d) { _ciJsonCache[url] = d; cb(d); })
        .catch(function() { cb([]); });
}

function _ciKnownTags(tagsUrl, cb) {
    var fromPage = Array.from(document.querySelectorAll('.tag-group-header[data-tag]'))
        .map(function(el) { return el.dataset.tag; })
        .filter(function(t) { return t && t !== '__untagged__'; });
    if (fromPage.length) { cb(fromPage); return; }
    _ciFetchJSON(tagsUrl, cb);
}

function parseTagsFromRaw(raw) {
    var tagMatches = (raw.match(/#\S+/g) || []).map(function(t) { return t.slice(1); });
    var assigneeMatches = (raw.match(/@\S+/g) || []).map(function(a) { return a.slice(1); });
    var text = raw.replace(/#\S+/g, '').replace(/@\S+/g, '').replace(/\s+/g, ' ').trim();
    return {tags: tagMatches, assignees: assigneeMatches, text: text};
}

function _ciParseText(canonical) {
    return canonical
        .replace(/#\S+/g, '')
        .replace(/@\S+/g, '')
        .replace(/\*[^#*\^~@]*?(?=\s*[#*\^~@]|$)/g, '')
        .replace(/\^[^#*\^~@]*?(?=\s*[#*\^~@]|$)/g, '')
        .replace(/~[^#*\^~@]*?(?=\s*[#*\^~@]|$)/g, '')
        .replace(/\s+/g, ' ')
        .trim();
}

// ---------------------------------------------------------------------------
// CompositeInput(containerEl, opts) — main factory
//
// opts: {
//   tags: bool (default true), note: bool, recurrence: bool, dueDate: bool, assignees: bool,
//   textOuter: Element,     — the contentEditable host div (required)
//   hiddenInput: Element,   — kept in sync with canonical string
//   quickPickEl: Element,   — quick-pick chip row
//   saveBtn: Element,       — shown when value diverges from canonical
//   form: Element,          — nearest form (default: containerEl.closest('form'))
//   canonical: string,      — initial canonical value (default: hiddenInput.value)
//   placeholder: string,
//   tagsUrl: string,        — /todos/tags.json or body[data-tags-url]
//   principalsUrl: string,  — /todos/principals.json
//   sessionKey: string,     — if set, tags persist in sessionStorage across HTMX reloads
// }
//
// Returns: {enterEditMode, exitEditMode, buildCompositeText, getPlainText, resetState}
// ---------------------------------------------------------------------------

function CompositeInput(containerEl, opts) {
    if (!containerEl || containerEl.dataset.ciInit) return null;
    containerEl.dataset.ciInit = '1';

    opts = opts || {};
    var enableTags      = opts.tags !== false;
    var enableNote      = !!opts.note;
    var enableRec       = !!opts.recurrence;
    var enableDate      = !!opts.dueDate;
    var enableAssignees = !!opts.assignees;

    var textOuter      = opts.textOuter;
    var hiddenInput    = opts.hiddenInput || null;
    var quickPickEl    = opts.quickPickEl || null;
    var saveBtn        = opts.saveBtn || null;
    var form           = opts.form || containerEl.closest('form');
    var tagsUrl        = opts.tagsUrl || (document.body && document.body.dataset.tagsUrl) || '';
    var principalsUrl  = opts.principalsUrl || '';
    var sessionKey     = opts.sessionKey || null;
    var _placeholder   = opts.placeholder || 'Add text…';

    var _initialCanonical = opts.canonical !== undefined
        ? opts.canonical
        : (hiddenInput ? hiddenInput.value : '');

    var tags      = sessionKey ? JSON.parse(sessionStorage.getItem(sessionKey) || '[]') : [];
    var assignees = [];
    var dateISO   = null;
    var dateLabel = null;
    var recLabel  = null;
    var noteText  = '';
    var _acMode   = null;

    var _savedTags      = null;
    var _savedDateISO   = null;
    var _savedRecLabel  = null;
    var _savedNoteText  = null;
    var _savedAssignees = null;
    var _editingId      = null;
    var _addUrl         = form ? form.getAttribute('hx-post') : null;

    // Parse initial canonical to seed state
    if (_initialCanonical) {
        (_initialCanonical.match(/#(\S+)/g) || []).forEach(function(m) {
            var t = m.slice(1);
            if (enableTags && tags.indexOf(t) === -1) tags.push(t);
        });
        if (enableRec) {
            var _rm = _initialCanonical.match(/\*([^#*\^~@]+?)(?=\s*[#*\^~@]|$)/);
            if (_rm) recLabel = _rm[1].trim();
        }
        if (enableNote) {
            var _nm = _initialCanonical.match(/~([^#*\^~@]+?)(?=\s*[#*\^~@]|$)/);
            if (_nm) noteText = _nm[1].trim();
        }
        if (enableDate) {
            var _dm = _initialCanonical.match(/\^([^#*\^~@]+?)(?=\s*[#*\^~@]|$)/);
            if (_dm) dateISO = _dm[1].trim();
        }
    }
    var _initialText = _ciParseText(_initialCanonical);

    // --- Segment helpers ---

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
    function getLastSeg()  { var s = getAllSegs(); return s[s.length - 1] || null; }

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

    function createAssigneePill(name) {
        var pill = document.createElement('span');
        pill.className = 'todo-assignee-pill';
        pill.dataset.pill = 'assignee';
        pill.dataset.assignee = name;
        pill.innerHTML = '@' + name + ' <button class="todo-assignee-remove" type="button" tabindex="-1" data-assignee="' + name + '">\xd7</button>';
        return pill;
    }

    function _formatDateLabel(iso) {
        var d = new Date(iso + 'T00:00:00');
        var weekday = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()];
        var month = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()];
        return weekday + ', ' + d.getDate() + ' ' + month;
    }

    function createDatePill() {
        var label = dateLabel || _formatDateLabel(dateISO);
        var pill = document.createElement('span');
        pill.className = 'todo-date-pill';
        pill.dataset.pill = 'date';
        pill.dataset.iso = dateISO;
        pill.title = dateISO;
        pill.innerHTML = '↗ ' + label + ' <button class="todo-date-remove" type="button" tabindex="-1" title="Remove date">\xd7</button>';
        return pill;
    }

    function createRecPill() {
        var pill = document.createElement('span');
        pill.className = 'todo-rec-pill';
        pill.dataset.pill = 'rec';
        pill.dataset.label = recLabel;
        pill.title = recLabel;
        pill.innerHTML = '↻ ' + recLabel + ' <button class="todo-rec-remove" type="button" tabindex="-1" title="Remove repeat">\xd7</button>';
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

    // --- Hidden input + save button sync ---

    function buildCompositeText() {
        var rawText = getPlainText();
        var typedTags = enableTags ? (rawText.match(/#\S+/g) || []).map(function(t) { return t.slice(1); }) : [];
        var allTags = tags.slice();
        typedTags.forEach(function(t) { if (allTags.indexOf(t) === -1) allTags.push(t); });
        var typedAssignees = enableAssignees ? (rawText.match(/@\S+/g) || []).map(function(a) { return a.slice(1); }) : [];
        var allAssignees = assignees.slice();
        typedAssignees.forEach(function(a) { if (allAssignees.indexOf(a) === -1) allAssignees.push(a); });
        var cleanText = rawText
            .replace(enableTags ? /#\S+/g : /(?!x)x/, '')
            .replace(enableAssignees ? /@\S+/g : /(?!x)x/, '')
            .replace(/\s+/g, ' ').trim();
        var parts = [cleanText]
            .concat(allTags.map(function(t) { return '#' + t; }))
            .concat(allAssignees.map(function(a) { return '@' + a; }));
        if (enableDate && dateISO) parts.push('^' + dateISO);
        if (enableRec && recLabel) parts.push('*' + recLabel);
        if (enableNote && noteText) parts.push('~' + noteText);
        return parts.join(' ').trim();
    }

    function syncHidden() {
        if (!hiddenInput) return;
        hiddenInput.value = buildCompositeText();
        if (saveBtn) {
            saveBtn.classList.toggle('d-none', hiddenInput.value === _initialCanonical);
        }
    }

    // --- Pill rendering ---

    function renderAllPills(overrideText) {
        var hadFocus = textOuter.contains(document.activeElement);
        var rawSaved = overrideText !== undefined ? overrideText :
            getAllSegs().map(function(s) { return s.textContent; }).join('');

        var pillList = [];
        if (enableTags) tags.forEach(function(tag) { pillList.push(createTagPill(tag)); });
        if (enableAssignees) assignees.forEach(function(name) { pillList.push(createAssigneePill(name)); });
        if (enableDate && dateISO) pillList.push(createDatePill());
        if (enableRec && recLabel) pillList.push(createRecPill());
        if (enableNote && noteText) pillList.push(createNotePill());

        var savedText = rawSaved.replace(/ /g, ' ').trimEnd();
        if (pillList.length > 0 && savedText.length > 0) savedText += ' ';

        textOuter.innerHTML = '';
        var firstSeg = createTextSeg(savedText);
        firstSeg.dataset.placeholder = _placeholder;
        textOuter.appendChild(firstSeg);

        pillList.forEach(function(pill) {
            textOuter.appendChild(pill);
            textOuter.appendChild(createTextSeg(''));
        });

        if (sessionKey) sessionStorage.setItem(sessionKey, JSON.stringify(tags));
        updateEmptyClass();
        syncHidden();
        if (hadFocus) focusLastSeg();
    }

    // --- Quick-pick ---

    function renderQuickPick() {
        if (!quickPickEl || !enableTags) return;
        quickPickEl.innerHTML = '';
        _ciKnownTags(tagsUrl, function(available) {
            var chips = available.filter(function(t) { return tags.indexOf(t) === -1; });
            if (!chips.length) { quickPickEl.style.display = 'none'; return; }
            chips.forEach(function(tag) {
                var chip = document.createElement('button');
                chip.type = 'button';
                chip.className = 'todo-quick-pick-chip';
                chip.textContent = '#' + tag;
                chip.addEventListener('click', function() { addTag(tag); focusLastSeg(); });
                quickPickEl.appendChild(chip);
            });
            quickPickEl.style.display = '';
        });
    }

    function showQuickPick() { if (quickPickEl && quickPickEl.children.length > 0) quickPickEl.style.display = ''; }
    function hideQuickPick() { if (quickPickEl) quickPickEl.style.display = 'none'; }

    if (quickPickEl) hideQuickPick();
    textOuter.addEventListener('focusin', function(e) {
        if (e.target.classList.contains('todo-text-seg')) { renderQuickPick(); showQuickPick(); }
    });
    textOuter.addEventListener('focusout', function() {
        setTimeout(function() { if (!textOuter.contains(document.activeElement)) hideQuickPick(); }, 150);
    });

    // --- State mutators ---

    function addTag(tag) {
        tag = tag.replace(/^#/, '');
        if (!tag || tags.indexOf(tag) !== -1) return;
        tags.push(tag);
        renderAllPills();
        renderQuickPick();
    }

    function removeTag(tag) {
        tags = tags.filter(function(t) { return t !== tag; });
        renderAllPills(); renderQuickPick(); focusLastSeg();
    }

    function addAssignee(name) {
        if (assignees.indexOf(name) === -1) { assignees.push(name); renderAllPills(); }
        focusLastSeg();
    }

    function removeAssignee(name) {
        assignees = assignees.filter(function(a) { return a !== name; });
        renderAllPills(); focusLastSeg();
    }

    function setDate(iso, label) { dateISO = iso || null; dateLabel = label || null; renderAllPills(); }
    function clearDate() { setDate(null, null); }

    function openDatePillPicker() {
        openPicker({anchorEl: containerEl, initialISO: dateISO, title: 'When is this due?',
            onCommit: function(iso) { setDate(iso, null); focusLastSeg(); },
            onCancel: function() { focusLastSeg(); }});
    }

    function setRecurrence(label) { recLabel = label || null; renderAllPills(); }
    function clearRecurrence() { setRecurrence(null); }

    function openRecurrencePillPicker() {
        openRecurrencePicker({anchorEl: containerEl, initialLabel: recLabel, title: 'Repeat',
            onCommit: function(label) { setRecurrence(label); focusLastSeg(); },
            onCancel: function() { focusLastSeg(); }});
    }

    function setNote(text) { noteText = text || ''; renderAllPills(); }
    function clearNote() { setNote(''); }

    function openNotePillPicker() {
        openNotePicker({anchorEl: containerEl, initialNote: noteText, title: 'Note',
            onCommit: function(text) { setNote(text); focusLastSeg(); },
            onCancel: function() { focusLastSeg(); }});
    }

    function removePillFromState(el) {
        if (el.dataset.pill === 'tag') removeTag(el.dataset.tag);
        else if (el.dataset.pill === 'assignee') removeAssignee(el.dataset.assignee);
        else if (el.dataset.pill === 'date') clearDate();
        else if (el.dataset.pill === 'rec') clearRecurrence();
        else if (el.dataset.pill === 'note') clearNote();
    }

    // --- Click handler ---

    containerEl.addEventListener('click', function(e) {
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
        var rmAssignee = e.target.closest('.todo-assignee-remove');
        if (rmAssignee) { e.stopPropagation(); removeAssignee(rmAssignee.dataset.assignee); return; }
        if (e.target.closest('.todo-tag-pill')) return;
        if (e.target.closest('.todo-assignee-pill')) return;
        if (!e.target.classList.contains('todo-text-seg')) focusLastSeg();
    });

    // --- Autocomplete ---

    var acEl = document.createElement('div');
    acEl.className = 'todo-tag-autocomplete';
    acEl.style.display = 'none';
    if (form) { form.style.position = 'relative'; form.appendChild(acEl); }
    else { containerEl.style.position = 'relative'; containerEl.appendChild(acEl); }
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

    function showAcPrincipals(matches) {
        if (!matches.length) { hideAc(); return; }
        _acMode = 'assignee';
        acSelected = -1;
        acEl.innerHTML = '';
        matches.forEach(function(p) {
            var item = document.createElement('div');
            item.className = 'todo-ac-item';
            item.textContent = '@' + p.name + (p.type === 'team' ? ' (team)' : '');
            item.dataset.assignee = p.name;
            item.addEventListener('mousedown', function(e) { e.preventDefault(); selectAcAssignee(p.name); });
            acEl.appendChild(item);
        });
        acEl.style.display = 'block';
    }

    function selectAcAssignee(name) {
        var sel = window.getSelection();
        if (sel && sel.rangeCount) {
            var range = sel.getRangeAt(0);
            if (range.startContainer.nodeType === Node.TEXT_NODE) {
                var tn = range.startContainer, pos = range.startOffset;
                var newBefore = tn.textContent.slice(0, pos).replace(/@\S*$/, '');
                tn.textContent = newBefore + tn.textContent.slice(pos);
                range.setStart(tn, newBefore.length); range.collapse(true);
                sel.removeAllRanges(); sel.addRange(range);
            }
        }
        hideAc();
        _acMode = null;
        addAssignee(name);
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

        if (enableAssignees) {
            var mAt = textBefore.match(/@(\S*)$/);
            if (mAt) {
                _acMode = 'assignee';
                var fragment = mAt[1];
                _ciFetchJSON(principalsUrl, function(principals) {
                    var scored = principals
                        .map(function(p) { return {name: p.name, type: p.type, score: fuzzyScore(fragment, p.name)}; })
                        .filter(function(p) { return p.score >= 0 && assignees.indexOf(p.name) === -1; });
                    scored.sort(function(a, b) { return a.score - b.score || a.name.localeCompare(b.name); });
                    showAcPrincipals(scored);
                });
                return;
            }
        }

        if (enableTags) {
            var m = textBefore.match(/#(\S*)$/);
            if (!m) { _acMode = null; hideAc(); return; }
            _acMode = 'tag';
            var frag = m[1];
            _ciKnownTags(tagsUrl, function(known) {
                var filtered = known.filter(function(t) { return tags.indexOf(t) === -1; });
                var scored = [];
                filtered.forEach(function(t) { var s = fuzzyScore(frag, t); if (s >= 0) scored.push({tag: t, score: s}); });
                scored.sort(function(a, b) { return a.score - b.score || a.tag.localeCompare(b.tag); });
                showAc(scored.map(function(x) { return x.tag; }));
            });
        } else {
            _acMode = null;
            hideAc();
        }
    }

    // --- Keyboard handling ---

    textOuter.addEventListener('keydown', function(e) {
        var activeSeg = getActiveSeg();
        if (!activeSeg) return;
        var items = acItems();

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
                e.preventDefault();
                if (_acMode === 'assignee') selectAcAssignee(items[acSelected].dataset.assignee);
                else selectAc(items[acSelected].dataset.tag);
                return;
            }
            if (e.key === 'Tab' && acSelected < 0 && items.length) {
                e.preventDefault();
                if (_acMode === 'assignee') selectAcAssignee(items[0].dataset.assignee);
                else selectAc(items[0].dataset.tag);
                return;
            }
            if (e.key === 'Escape') { hideAc(); return; }
        }

        if (e.key === 'Enter') {
            e.preventDefault();
            if (form) form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
            return;
        }

        if (e.key === 'Escape') {
            if (_editingId) exitEditMode();
            activeSeg.blur();
            return;
        }

        var segs = getAllSegs(), idx = segs.indexOf(activeSeg);

        if (e.key === 'ArrowRight' && e.metaKey) { e.preventDefault(); focusLastSeg(); return; }
        if (e.key === 'ArrowLeft' && e.metaKey) {
            e.preventDefault();
            var first = getFirstSeg();
            if (first) { first.focus(); placeCursorAtStart(first); }
            return;
        }
        if (e.key === 'a' && e.metaKey) {
            e.preventDefault();
            var firstS = getFirstSeg(), lastS = getLastSeg();
            if (!firstS || !lastS) return;
            var selRange = document.createRange();
            selRange.setStart(firstS, 0); selRange.setEnd(lastS, lastS.childNodes.length);
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
        if (e.key === 'Backspace' && idx > 0 && isAtStart(activeSeg)) {
            var prevPill = activeSeg.previousElementSibling;
            if (prevPill && prevPill.dataset && prevPill.dataset.pill) {
                e.preventDefault(); removePillFromState(prevPill); return;
            }
        }
    });

    textOuter.addEventListener('focusout', function() { setTimeout(hideAc, 150); });

    // --- Input event ---

    textOuter.addEventListener('input', function(e) {
        if (!e.target.classList.contains('todo-text-seg')) return;
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) { updateAc(); updateEmptyClass(); syncHidden(); return; }
        var range = sel.getRangeAt(0);
        var tn = range.startContainer, pos = range.startOffset;

        if (tn.nodeType === Node.TEXT_NODE && tn.parentNode === e.target) {
            var text = tn.textContent;
            var before = text.slice(0, pos);
            var lastChar = before.slice(-1);

            if ((lastChar === '^' && enableDate) || (lastChar === '*' && enableRec) || (lastChar === '~' && enableNote)) {
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

            if (enableTags) {
                var m = before.replace(/ /g, ' ').match(/#(\S+) $/);
                if (m) {
                    var tag = m[1], removeLen = m[0].length;
                    var beforeText = text.slice(0, pos - removeLen).replace(/\s+$/, ' ');
                    tn.textContent = beforeText + ' ' + text.slice(pos);
                    var newPos = beforeText.length + 1;
                    range.setStart(tn, newPos); range.collapse(true);
                    sel.removeAllRanges(); sel.addRange(range);
                    hideAc(); _acMode = null; addTag(tag); updateEmptyClass();
                    return;
                }
            }

            if (enableAssignees) {
                var mAt = before.replace(/ /g, ' ').match(/@(\S+) $/);
                if (mAt) {
                    var principal = mAt[1], removeLenAt = mAt[0].length;
                    var beforeTextAt = text.slice(0, pos - removeLenAt).replace(/\s+$/, ' ');
                    tn.textContent = beforeTextAt + ' ' + text.slice(pos);
                    var newPosAt = beforeTextAt.length + 1;
                    range.setStart(tn, newPosAt); range.collapse(true);
                    sel.removeAllRanges(); sel.addRange(range);
                    hideAc(); _acMode = null; addAssignee(principal); updateEmptyClass();
                    return;
                }
            }
        }

        updateAc();
        updateEmptyClass();
        syncHidden();
    });

    // Strip rich formatting on paste
    textOuter.addEventListener('paste', function(e) {
        if (!e.target.classList.contains('todo-text-seg')) return;
        e.preventDefault();
        var pastedText = (e.clipboardData || window.clipboardData).getData('text/plain');
        if (!pastedText) return;
        var sel = window.getSelection();
        if (!sel || !sel.rangeCount) return;
        var range = sel.getRangeAt(0);
        range.deleteContents();
        var inserted = document.createTextNode(pastedText);
        range.insertNode(inserted);
        range.setStartAfter(inserted); range.collapse(true);
        sel.removeAllRanges(); sel.addRange(range);
        e.target.dispatchEvent(new Event('input', {bubbles: true}));
    });

    // --- Edit mode (used by todo form to switch between add/edit) ---

    function enterEditMode(id, text, tagList, dueDate, recurrence, editUrl, note, assigneeList) {
        _savedTags = tags.slice();
        _savedDateISO = dateISO;
        _savedRecLabel = recLabel;
        _savedNoteText = noteText;
        _savedAssignees = assignees.slice();
        _editingId = id;
        if (enableTags) tags = tagList.slice();
        if (enableAssignees) assignees = (assigneeList || []).slice();
        if (enableDate) { dateISO = dueDate || null; dateLabel = null; }
        if (enableRec) recLabel = recurrence || null;
        if (enableNote) noteText = note || '';
        _placeholder = 'Edit todo…';
        renderAllPills(text || '');
        if (form && editUrl) { form.setAttribute('hx-post', editUrl); if (window.htmx) htmx.process(form); }
        containerEl.classList.add('todo-tag-input--editing');
        var firstSeg = getFirstSeg();
        if (firstSeg) { firstSeg.focus(); setTimeout(function() { placeCursorAtEnd(firstSeg); }, 0); }
        renderQuickPick();
    }

    function exitEditMode() {
        _editingId = null;
        if (enableTags) { tags = _savedTags !== null ? _savedTags : []; _savedTags = null; }
        if (enableAssignees) { assignees = _savedAssignees !== null ? _savedAssignees : []; _savedAssignees = null; }
        if (enableDate) { dateISO = _savedDateISO; dateLabel = null; _savedDateISO = null; }
        if (enableRec) { recLabel = _savedRecLabel; _savedRecLabel = null; }
        if (enableNote) { noteText = _savedNoteText !== null ? _savedNoteText : ''; _savedNoteText = null; }
        _placeholder = opts.placeholder || 'New todo…';
        renderAllPills('');
        renderQuickPick();
        if (form && _addUrl) { form.setAttribute('hx-post', _addUrl); if (window.htmx) htmx.process(form); }
        containerEl.classList.remove('todo-tag-input--editing');
    }

    function resetState() {
        tags = sessionKey ? JSON.parse(sessionStorage.getItem(sessionKey) || '[]') : [];
        assignees = [];
        dateISO = null; dateLabel = null; recLabel = null; noteText = '';
        _editingId = null;
    }

    // --- Initial render ---
    renderAllPills(_initialText);
    if (quickPickEl) renderQuickPick();

    function clearVolatileState() {
        assignees = [];
        dateISO = null; dateLabel = null; recLabel = null; noteText = '';
        if (sessionKey) sessionStorage.setItem(sessionKey, JSON.stringify(tags));
    }

    function restoreFromRaw(raw) {
        var parsed = parseTagsFromRaw(raw);
        parsed.tags.forEach(function(t) { if (tags.indexOf(t) === -1) tags.push(t); });
        parsed.assignees.forEach(function(a) { if (assignees.indexOf(a) === -1) assignees.push(a); });
        renderAllPills(parsed.text || '');
        renderQuickPick();
        var first = getFirstSeg();
        if (first) { first.focus(); placeCursorAtEnd(first); }
    }

    return {
        enterEditMode: enterEditMode,
        exitEditMode: exitEditMode,
        buildCompositeText: buildCompositeText,
        getPlainText: getPlainText,
        resetState: resetState,
        clearVolatileState: clearVolatileState,
        restoreFromRaw: restoreFromRaw,
        getEditingId: function() { return _editingId; },
        getTags: function() { return tags; },
        getAssignees: function() { return assignees; },
        focusLast: focusLastSeg,
        focusFirst: focusFirstSeg,
    };
}
