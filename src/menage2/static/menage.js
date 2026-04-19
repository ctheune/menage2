
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
        swipePost(list.dataset.postponeUrl, todoId, list);
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
    var savedTags = null; // tags saved before entering edit mode
    var editingId = null;

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

    function showQuickPick() { if (quickPick) quickPick.style.display = ''; }
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

    container.addEventListener('click', function(e) {
        var btn = e.target.closest('.todo-tag-remove');
        if (btn) { removeTag(btn.dataset.tag); return; }
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
    function enterEditMode(id, text, tagList, editUrl) {
        savedTags = tags.slice();
        editingId = id;
        tags = tagList.slice();
        renderPills();
        renderQuickPick();
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
        textInput.value = '';
        form.setAttribute('hx-post', addUrl);
        htmx.process(form);
        container.classList.remove('todo-tag-input--editing');
        textInput.placeholder = 'New todo\u2026';
    }

    document.addEventListener('todoEditStart', function(e) {
        var d = e.detail;
        enterEditMode(d.id, d.text, d.tags, d.editUrl);
    });

    textInput.addEventListener('input', function() {
        var val = textInput.value;
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
        return [cleanText].concat(allTags.map(function(t) { return '#' + t; })).join(' ').trim();
    }

    // Capture phase: compute the composite text while the input still has the user's value,
    // then clear the input and reset state. htmx:configRequest (below) injects it into the request.
    form.addEventListener('submit', function() {
        hideAc();
        _pendingText = buildCompositeText();
        if (editingId) {
            tags = savedTags !== null ? savedTags : [];
            savedTags = null;
            editingId = null;
            container.classList.remove('todo-tag-input--editing');
            textInput.placeholder = 'New todo\u2026';
        }
        sessionStorage.setItem('todo-tags', JSON.stringify(tags));
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
}

// Show error toast when todo text is empty (only tags entered)
document.body.addEventListener('showAddTodoError', function(e) {
    var existing = document.getElementById('error-toast');
    if (existing) existing.remove();

    var toast = document.createElement('div');
    toast.id = 'error-toast';
    toast.className = 'fixed bottom-6 left-6 rounded-xl z-[9999] text-base font-semibold';
    toast.style.cssText = 'background:#dc2626;color:#fff;padding:0.875rem 1.25rem;box-shadow:0 8px 32px rgba(0,0,0,0.45),0 2px 8px rgba(0,0,0,0.3);pointer-events:none;';
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
    toast.className = 'undo-toast rounded-xl text-base font-semibold cursor-pointer';
    toast.style.cssText = 'background:#fef3c7;color:#78350f;border:1px solid #f59e0b;padding:0.875rem 1.25rem;box-shadow:0 8px 32px rgba(0,0,0,0.2),0 2px 8px rgba(0,0,0,0.1);';
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
    toast.style.background = '#65a30d';
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

    // 'r' key: batch-restore checked items on the done list
    if (e.key === 'r') {
        var doneList = document.getElementById('done-list');
        if (!doneList) return;
        var boxes = Array.from(document.querySelectorAll('input.todo-checkbox:checked'));
        if (boxes.length === 0) return;
        e.preventDefault();
        var ids = boxes.map(function(b) { return b.dataset.id; }).join(',');
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
            editUrl: li.dataset.editUrl || ''
        }}));
        return;
    }

    var list = document.getElementById('todo-list');
    if (!list) return;

    var key = e.key;

    if (key === 'c' || key === 'p') {
        var boxes = Array.from(document.querySelectorAll('input.todo-checkbox:checked'));
        // Fall back to hovered item if nothing is checked
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

        if (key === 'c') {
            htmx.ajax('POST', list.dataset.doneUrl,
                       {target: list, swap: 'innerHTML', values: {todo_ids: ids}});
        } else {
            htmx.ajax('POST', list.dataset.postponeUrl,
                       {target: list, swap: 'innerHTML', values: {todo_ids: ids}});
        }
    }

    if (e.shiftKey && key === 'P') {
        var pausedBtn = document.querySelector('button[hx-post*="activate-postponed"]');
        if (pausedBtn) { e.preventDefault(); pausedBtn.click(); }
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

// --- Keyboard shortcut help overlay ---
(function() {
    var overlay = document.createElement('div');
    overlay.id = 'kbd-help-overlay';
    overlay.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:9999;align-items:center;justify-content:center;';
    overlay.innerHTML = [
        '<div style="background:#fff;border-radius:0.75rem;padding:1.5rem 2rem;max-width:26rem;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.2);">',
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
        _kbdRow('p', 'Postpone hovered / selected'),
        _kbdRow('Shift+P', 'Unpause all postponed items'),
        _kbdRow('u', 'Undo last action'),
        '</tbody></table>',

        _kbdSection('Done list'),
        '<table style="width:100%;border-collapse:collapse;font-size:0.875rem;margin-bottom:0.25rem;"><tbody>',
        _kbdRow('click', 'Select / deselect item'),
        _kbdRow('r', 'Restore selected items'),
        '</tbody></table>',

        '</div>'
    ].join('');
    document.body.appendChild(overlay);

    function _kbdSection(title) {
        return '<p style="font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#94a3b8;margin:0 0 0.35rem;">' + title + '</p>';
    }

    function _kbdRow(key, desc) {
        return '<tr><td style="padding:0.25rem 0.75rem 0.25rem 0;white-space:nowrap;">'
             + '<kbd style="background:#f1f5f9;border:1px solid #cbd5e1;border-radius:0.25rem;padding:0.1rem 0.4rem;font-family:monospace;font-size:0.8rem;">'
             + key + '</kbd></td>'
             + '<td style="padding:0.25rem 0;color:#374151;">' + desc + '</td></tr>';
    }

    function showHelp() {
        overlay.style.display = 'flex';
    }
    function hideHelp() {
        overlay.style.display = 'none';
    }

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) hideHelp();
    });

    document.addEventListener('keydown', function(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.key === '?') { e.preventDefault(); showHelp(); return; }
        if (e.key === 'Escape') { hideHelp(); }
    });
}());

htmx.onLoad(function(content) {
    initSortables(content);
    initTodoSwipe(content);
    initTagInput();
});
initSortables(document);
initTodoSwipe(document);
initTagInput();
