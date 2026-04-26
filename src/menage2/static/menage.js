
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

// Delegated handler for the edit pencil button — fires todoEditStart event
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

    var textInput = document.getElementById('todo-text');
    var hiddenInput = document.getElementById('todo-hidden-text');
    var form = document.getElementById('todo-form');
    var quickPick = document.getElementById('todo-quick-pick');

    var tags = JSON.parse(sessionStorage.getItem('todo-tags') || '[]');
    var addUrl = form.getAttribute('hx-post');
    var savedTags = null;       // tags saved before entering edit mode
    var savedDateISO = null;    // due-date saved before entering edit mode
    var savedRecLabel = null;   // recurrence saved before entering edit mode
    var editingId = null;
    var dateISO = null;         // currently-attached due date (ISO string or null)
    var dateLabel = null;       // human-friendly label cached from the picker
    var recLabel = null;        // currently-attached recurrence label (text)

    function renderPills() {
        container.querySelectorAll('.todo-tag-pill').forEach(function(el) { el.remove(); });
        tags.forEach(function(tag) {
            var pill = document.createElement('span');
            pill.className = 'todo-tag-pill';
            pill.innerHTML = '#' + tag + ' <button class="todo-tag-remove" type="button" data-tag="' + tag + '">\u00d7</button>';
            container.insertBefore(pill, textInput);
        });
        sessionStorage.setItem('todo-tags', JSON.stringify(tags));
    }

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
    textInput.addEventListener('focus', showQuickPick);
    textInput.addEventListener('blur', function() { setTimeout(hideQuickPick, 150); });

    function addTag(tag) {
        tag = tag.replace(/^#/, '');
        if (tags.indexOf(tag) === -1) {
            tags.push(tag);
            renderPills();
            renderQuickPick();
        }
        textInput.focus();
    }

    function removeTag(tag) {
        tags = tags.filter(function(t) { return t !== tag; });
        renderPills();
        renderQuickPick();
    }

    // --- Date pill (the ^ marker) ---
    function _formatDateLabel(iso) {
        // Best-effort fallback when the picker didn't supply a label (e.g. when
        // the pill is rebuilt from the data-due-date attribute on edit).
        var d = new Date(iso + 'T00:00:00');
        var weekday = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()];
        var month = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()];
        return weekday + ', ' + d.getDate() + ' ' + month;
    }

    function renderDatePill() {
        container.querySelectorAll('.todo-date-pill').forEach(function(el) { el.remove(); });
        if (!dateISO) return;
        var label = dateLabel || _formatDateLabel(dateISO);
        var pill = document.createElement('span');
        pill.className = 'todo-date-pill';
        pill.dataset.iso = dateISO;
        pill.title = dateISO;
        pill.innerHTML = '↗ ' + label
            + ' <button class="todo-date-remove" type="button" title="Remove date">×</button>';
        // Insert before the text input so it sits visually with other pills.
        container.insertBefore(pill, textInput);
    }

    function setDate(iso, label) {
        dateISO = iso || null;
        dateLabel = label || null;
        renderDatePill();
    }

    function clearDate() { setDate(null, null); }

    function openDatePillPicker() {
        openPicker({
            anchorEl: container,
            initialISO: dateISO,
            title: 'When is this due?',
            onCommit: function(iso) {
                setDate(iso, null);
                textInput.focus();
            },
            onCancel: function() {
                textInput.focus();
            }
        });
    }

    // --- Recurrence pill (the * marker) ---
    function renderRecPill() {
        container.querySelectorAll('.todo-rec-pill').forEach(function(el) { el.remove(); });
        if (!recLabel) return;
        var pill = document.createElement('span');
        pill.className = 'todo-rec-pill';
        pill.dataset.label = recLabel;
        pill.title = recLabel;
        pill.innerHTML = '↻ ' + recLabel
            + ' <button class="todo-rec-remove" type="button" title="Remove repeat">×</button>';
        container.insertBefore(pill, textInput);
    }

    function setRecurrence(label) {
        recLabel = label || null;
        renderRecPill();
    }

    function clearRecurrence() { setRecurrence(null); }

    function openRecurrencePillPicker() {
        openRecurrencePicker({
            anchorEl: container,
            initialLabel: recLabel,
            title: 'Repeat',
            onCommit: function(label) {
                setRecurrence(label);
                textInput.focus();
            },
            onCancel: function() {
                textInput.focus();
            }
        });
    }

    container.addEventListener('click', function(e) {
        var rmTag = e.target.closest('.todo-tag-remove');
        if (rmTag) { removeTag(rmTag.dataset.tag); return; }
        var rmDate = e.target.closest('.todo-date-remove');
        if (rmDate) { e.stopPropagation(); clearDate(); return; }
        var datePill = e.target.closest('.todo-date-pill');
        if (datePill) { e.stopPropagation(); openDatePillPicker(); return; }
        var rmRec = e.target.closest('.todo-rec-remove');
        if (rmRec) { e.stopPropagation(); clearRecurrence(); return; }
        var recPill = e.target.closest('.todo-rec-pill');
        if (recPill) { e.stopPropagation(); openRecurrencePillPicker(); return; }
        textInput.focus();
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
            item.addEventListener('mousedown', function(e) {
                e.preventDefault();
                selectAc(tag);
            });
            acEl.appendChild(item);
        });
        acEl.style.display = 'block';
    }

    function selectAc(tag) {
        var val = textInput.value;
        var cursor = textInput.selectionStart;
        var before = val.slice(0, cursor).replace(/#\S*$/, '');
        var after = val.slice(cursor);
        textInput.value = (before + after).replace(/  +/g, ' ');
        hideAc();
        addTag(tag);
    }

    function fuzzyScore(fragment, tag) {
        if (!fragment) return 2;
        var f = fragment.toLowerCase(), t = tag.toLowerCase();
        if (t.startsWith(f)) return 0;
        if (t.split(':').some(function(s) { return s.startsWith(f); })) return 1;
        // subsequence match: every char of f must appear in t in order
        var fi = 0;
        for (var ti = 0; ti < t.length && fi < f.length; ti++) {
            if (t[ti] === f[fi]) fi++;
        }
        return fi === f.length ? 2 : -1;
    }

    function updateAc() {
        var val = textInput.value;
        var cursor = textInput.selectionStart;
        var before = val.slice(0, cursor);
        var m = before.match(/#(\S*)$/);
        if (!m) { hideAc(); return; }
        var fragment = m[1];
        var known = Array.from(document.querySelectorAll('.tag-group-header[data-tag]'))
            .map(function(el) { return el.dataset.tag; })
            .filter(function(t) { return t && t !== '__untagged__' && tags.indexOf(t) === -1; });
        var scored = [];
        known.forEach(function(t) {
            var s = fuzzyScore(fragment, t);
            if (s >= 0) scored.push({tag: t, score: s});
        });
        scored.sort(function(a, b) { return a.score - b.score || a.tag.localeCompare(b.tag); });
        showAc(scored.map(function(x) { return x.tag; }));
    }

    textInput.addEventListener('keydown', function(e) {
        var items = acItems();
        if (acEl.style.display === 'none' || !items.length) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            acSelected = Math.min(acSelected + 1, items.length - 1);
            items.forEach(function(el, i) { el.classList.toggle('todo-ac-selected', i === acSelected); });
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            acSelected = Math.max(acSelected - 1, -1);
            items.forEach(function(el, i) { el.classList.toggle('todo-ac-selected', i === acSelected); });
        } else if ((e.key === 'Enter' || e.key === 'Tab') && acSelected >= 0) {
            e.preventDefault();
            selectAc(items[acSelected].dataset.tag);
        } else if (e.key === 'Tab' && acSelected < 0 && items.length) {
            e.preventDefault();
            selectAc(items[0].dataset.tag);
        } else if (e.key === 'Escape') {
            hideAc();
        }
    });

    textInput.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            if (acEl.style.display === 'none' && editingId) exitEditMode();
            textInput.blur();
        }
    });

    textInput.addEventListener('blur', function() { setTimeout(hideAc, 150); });

    // --- Edit mode ---
    function enterEditMode(id, text, tagList, dueDate, recurrence, editUrl) {
        savedTags = tags.slice();
        savedDateISO = dateISO;
        savedRecLabel = recLabel;
        editingId = id;
        tags = tagList.slice();
        renderPills();
        renderQuickPick();
        setDate(dueDate || null, null);
        setRecurrence(recurrence || null);
        textInput.value = text;
        form.setAttribute('hx-post', editUrl);
        htmx.process(form);
        container.classList.add('todo-tag-input--editing');
        textInput.placeholder = 'Edit todo\u2026';
        textInput.focus();
    }

    function exitEditMode() {
        editingId = null;
        tags = savedTags !== null ? savedTags : [];
        savedTags = null;
        renderPills();
        renderQuickPick();
        setDate(savedDateISO, null);
        savedDateISO = null;
        setRecurrence(savedRecLabel);
        savedRecLabel = null;
        textInput.value = '';
        form.setAttribute('hx-post', addUrl);
        htmx.process(form);
        container.classList.remove('todo-tag-input--editing');
        textInput.placeholder = 'New todo\u2026';
    }

    document.addEventListener('todoEditStart', function(e) {
        var d = e.detail;
        enterEditMode(d.id, d.text, d.tags, d.dueDate, d.recurrence, d.editUrl);
    });

    textInput.addEventListener('input', function() {
        var val = textInput.value;

        // ^ \u2192 open date picker, strip the marker from the input
        var caretIdx = val.indexOf('^');
        if (caretIdx !== -1) {
            textInput.value = val.slice(0, caretIdx) + val.slice(caretIdx + 1);
            hideAc();
            openDatePillPicker();
            return;
        }

        // * \u2192 open recurrence picker, strip the marker
        var starIdx = val.indexOf('*');
        if (starIdx !== -1) {
            textInput.value = val.slice(0, starIdx) + val.slice(starIdx + 1);
            hideAc();
            openRecurrencePillPicker();
            return;
        }

        var re = /#(\S+) /g;
        var match;
        var extracted = [];
        while ((match = re.exec(val)) !== null) {
            extracted.push(match[1]);
        }
        if (extracted.length > 0) {
            textInput.value = val.replace(/#\S+ /g, '').replace(/  +/g, ' ');
            extracted.forEach(addTag);
            hideAc();
        } else {
            updateAc();
        }
    });

    var _pendingText = null;

    function buildCompositeText() {
        var rawText = textInput.value;
        var typedTags = (rawText.match(/#\S+/g) || []).map(function(t) { return t.slice(1); });
        var allTags = tags.slice();
        typedTags.forEach(function(t) { if (allTags.indexOf(t) === -1) allTags.push(t); });
        var cleanText = rawText.replace(/#\S+/g, '').replace(/\s+/g, ' ').trim();
        var parts = [cleanText].concat(allTags.map(function(t) { return '#' + t; }));
        if (dateISO) parts.push('^' + dateISO);
        if (recLabel) parts.push('*' + recLabel);
        return parts.join(' ').trim();
    }

    // Capture phase: compute the composite text while the input still has the user's value,
    // then clear the input and reset state. htmx:configRequest (below) injects it into the request.
    form.addEventListener('submit', function() {
        hideAc();
        _pendingText = buildCompositeText();
        if (editingId) {
            tags = savedTags !== null ? savedTags : [];
            savedTags = null;
            savedDateISO = null;
            editingId = null;
            container.classList.remove('todo-tag-input--editing');
            textInput.placeholder = 'New todo\u2026';
        }
        sessionStorage.setItem('todo-tags', JSON.stringify(tags));
        clearDate();
        clearRecurrence();
        textInput.value = '';
    }, true);

    // htmx:configRequest fires just before HTMX sends the request, after form serialization.
    // Override the text parameter here so it always reflects the composite widget value.
    form.addEventListener('htmx:configRequest', function(e) {
        if (_pendingText !== null) {
            e.detail.parameters['text'] = _pendingText;
            _pendingText = null;
        }
    });

    // After successful submit (body swap), tags remain in sessionStorage and re-render on next initTagInput call.
    // On error, restore text + accumulated tags into composite widget.
    document.body.addEventListener('showAddTodoError', function(e) {
        var raw = e.detail.input || '';
        var parsed = parseTagsFromRaw(raw);
        parsed.tags.forEach(function(t) { if (tags.indexOf(t) === -1) tags.push(t); });
        renderPills();
        renderQuickPick();
        textInput.value = parsed.text;
        textInput.focus();
    }, true);

    renderPills();
    renderQuickPick();
    renderDatePill();
    renderRecPill();
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
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

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
//   mode: 'pill'    → onCommit(iso, label) — caller inserts a pill
//         'set-due' → caller does whatever it wants on commit (we just call
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
    input.placeholder = 'tomorrow / next wed / 2026-05-12 …';
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
        prev.textContent = '‹';
        prev.style.cssText = 'background:none;border:none;cursor:pointer;font-size:1rem;color:inherit;padding:0 0.5rem;';
        prev.addEventListener('click', function() {
            pendingMonth.setMonth(pendingMonth.getMonth() - 1);
            renderCalendar();
        });
        var next = document.createElement('button');
        next.type = 'button';
        next.textContent = '›';
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
                        preview.textContent = '→ ' + data.label + ' (' + data.date + ')';
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
        title: 'Postpone…',
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
    input.placeholder = 'every wednesday / after 10 days / every 15th …';
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
                        preview.textContent = '↻ ' + data.label;
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
        _kbdRow('Shift+P', 'Postpone… (chip palette + calendar)'),
        _kbdRow('u', 'Undo last action'),
        _kbdRow('click ↻', 'Show repetition history for this item'),
        '</tbody></table>',

        _kbdSection('Adding / editing a todo'),
        '<table style="width:100%;border-collapse:collapse;font-size:0.875rem;margin-bottom:1rem;"><tbody>',
        _kbdRow('#tag', 'Attach a tag (single word)'),
        _kbdRow('^', 'Open the date picker — commits as a pill'),
        _kbdRow('*', 'Open the repetition picker — commits as a pill'),
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

// Bound once on document — never replaced by HTMX. `?` should fire even when
// the user is mid-typing in the add-todo input: opening help shouldn't depend
// on what's focused.
document.addEventListener('keydown', function(e) {
    if (e.key === '?') { e.preventDefault(); showHelp(); return; }
    if (e.key === 'Escape' && _helpOverlay && _helpOverlay.style.display === 'flex') {
        e.preventDefault();
        hideHelp();
    }
});

htmx.onLoad(function(content) {
    ensureHelpOverlay();
    initSortables(content);
    initTodoSwipe(content);
    initTagInput();
});
ensureHelpOverlay();
initSortables(document);
initTodoSwipe(document);
initTagInput();
