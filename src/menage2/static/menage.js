
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
    htmx.ajax('POST', url, {target: list, swap: 'innerHTML', values: {todo_ids: todoId}});
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

function initTodoSwipe(content) {
    content.querySelectorAll('.todo-item').forEach(function(item) {
        var startX = 0, dx = 0;
        var THRESHOLD = 80;

        item.addEventListener('touchstart', function(e) {
            startX = e.touches[0].clientX;
            item.style.transition = 'none';
        }, {passive: true});

        item.addEventListener('touchmove', function(e) {
            dx = e.touches[0].clientX - startX;
            var clamped = Math.max(-150, Math.min(150, dx));
            item.style.transform = 'translateX(' + clamped + 'px)';
            item.dataset.swipeDir = dx > 0 ? 'right' : (dx < 0 ? 'left' : '');
        }, {passive: true});

        item.addEventListener('click', function(e) {
            var checkbox = item.querySelector('.todo-checkbox');
            if (!checkbox || e.target === checkbox) return;
            checkbox.checked = !checkbox.checked;
        });

        item.addEventListener('touchend', function() {
            item.style.transition = 'transform 0.2s ease';
            var list = document.getElementById('todo-list');
            var checkbox = item.querySelector('.todo-checkbox');
            var todoId = checkbox ? checkbox.dataset.id : null;
            if (dx >= THRESHOLD && list && todoId) {
                item.style.transform = 'translateX(100vw)';
                swipePost(list.dataset.doneUrl, todoId, list);
            } else if (dx <= -THRESHOLD && list && todoId) {
                item.style.transform = 'translateX(-100vw)';
                swipePost(list.dataset.postponeUrl, todoId, list);
            } else {
                item.style.transform = 'translateX(0)';
                delete item.dataset.swipeDir;
            }
            dx = 0;
        });
    });
}

function parseTagsFromRaw(raw) {
    var tagMatches = (raw.match(/#\S+/g) || []).map(function(t) { return t.slice(1); });
    var text = raw.replace(/#\S+/g, '').replace(/\s+/g, ' ').trim();
    return { tags: tagMatches, text: text };
}

function initTagInput() {
    var container = document.getElementById('todo-tag-input');
    if (!container) return;

    var textInput = document.getElementById('todo-text');
    var hiddenInput = document.getElementById('todo-hidden-text');
    var form = document.getElementById('todo-form');
    var quickPick = document.getElementById('todo-quick-pick');

    var tags = JSON.parse(sessionStorage.getItem('todo-tags') || '[]');

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

    // Capture phase fires before HTMX's bubble-phase submit handler serializes the form.
    form.addEventListener('submit', function() {
        var rawText = textInput.value;
        var typedTags = (rawText.match(/#\S+/g) || []).map(function(t) { return t.slice(1); });
        typedTags.forEach(function(t) { if (tags.indexOf(t) === -1) tags.push(t); });
        var cleanText = rawText.replace(/#\S+/g, '').replace(/\s+/g, ' ').trim();
        hiddenInput.value = [cleanText].concat(tags.map(function(t) { return '#' + t; })).join(' ').trim();
        sessionStorage.setItem('todo-tags', JSON.stringify(tags));
        textInput.value = '';
    }, true);

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
    toast.style.cssText = 'background:#f97316;color:#fff;padding:0.875rem 1.25rem;box-shadow:0 8px 32px rgba(0,0,0,0.35),0 2px 8px rgba(0,0,0,0.2);';
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

    var list = document.getElementById('todo-list');
    if (!list) return;

    var key = e.key;

    if (key === 'c' || key === 'p') {
        var boxes = Array.from(document.querySelectorAll('input.todo-checkbox:checked'));
        if (boxes.length === 0) return;
        e.preventDefault();

        var ids = boxes.map(function(b) { return b.dataset.id; }).join(',');
        if (key === 'c') {
            htmx.ajax('POST', list.dataset.doneUrl,
                       {target: list, swap: 'innerHTML', values: {todo_ids: ids}});
        } else {
            htmx.ajax('POST', list.dataset.postponeUrl,
                       {target: list, swap: 'innerHTML', values: {todo_ids: ids}});
        }
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

htmx.onLoad(function(content) {
    initSortables(content);
    initTodoSwipe(content);
    initTagInput();
});
initSortables(document);
initTodoSwipe(document);
initTagInput();
