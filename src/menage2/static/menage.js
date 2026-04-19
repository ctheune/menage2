
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

        item.addEventListener('touchend', function() {
            item.style.transition = 'transform 0.2s ease';
            if (dx >= THRESHOLD && item.dataset.doneUrl) {
                item.style.transform = 'translateX(100vw)';
                htmx.ajax('POST', item.dataset.doneUrl, {target: item, swap: 'delete'});
            } else if (dx <= -THRESHOLD && item.dataset.postponeUrl) {
                item.style.transform = 'translateX(-100vw)';
                htmx.ajax('POST', item.dataset.postponeUrl, {target: item, swap: 'delete'});
            } else {
                item.style.transform = 'translateX(0)';
                delete item.dataset.swipeDir;
            }
            dx = 0;
        });
    });
}

// Show error toast when todo text is empty (only tags entered)
document.body.addEventListener('showAddTodoError', function(e) {
    var input = document.querySelector('input[name="text"]');
    if (input) {
        input.value = e.detail.input;
        input.focus();
        input.select();
    }

    var existing = document.getElementById('error-toast');
    if (existing) existing.remove();

    var toast = document.createElement('div');
    toast.id = 'error-toast';
    toast.className = 'fixed bottom-4 left-4 bg-red-600 text-white px-4 py-2 rounded-lg shadow-lg z-50 text-sm';
    toast.textContent = 'A todo needs text, not just tags.';
    document.body.appendChild(toast);
    setTimeout(function() { toast.remove(); }, 3000);
});

// Show undo toast when server fires showUndoToast HX-Trigger event
document.body.addEventListener('showUndoToast', function(e) {
    var existing = document.getElementById('undo-toast');
    if (existing) existing.remove();

    var toast = document.createElement('div');
    toast.id = 'undo-toast';
    toast.dataset.todoIds = e.detail.ids;
    toast.dataset.prevStatus = e.detail.prevStatus;
    toast.className = 'fixed bottom-4 right-4 bg-slate-800 text-white px-4 py-2 rounded-lg shadow-lg cursor-pointer z-50 text-sm';
    toast.textContent = 'Undo (u)';

    toast.addEventListener('click', function() {
        document.dispatchEvent(new KeyboardEvent('keydown', {key: 'u', bubbles: true}));
    });

    document.body.appendChild(toast);
    setTimeout(function() {
        if (document.getElementById('undo-toast') === toast) {
            toast.remove();
        }
    }, 4000);
});

document.addEventListener('keydown', function(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    var list = document.getElementById('todo-list');
    if (!list) return;

    var key = e.key;

    if (key === 'c' || key === 'p') {
        var boxes = Array.from(document.querySelectorAll('input.todo-checkbox:checked'));
        if (boxes.length === 0) return;
        e.preventDefault();

        if (key === 'c') {
            if (boxes.length === 1) {
                var item = boxes[0].closest('.todo-item');
                htmx.ajax('POST', item.dataset.doneUrl, {target: item, swap: 'delete'});
            } else {
                var ids = boxes.map(function(b) { return b.dataset.id; }).join(',');
                htmx.ajax('POST', list.dataset.batchDoneUrl,
                           {target: list, swap: 'innerHTML', values: {todo_ids: ids}});
            }
        } else {
            // 'p' — postpone single checked item
            var item = boxes[0].closest('.todo-item');
            htmx.ajax('POST', item.dataset.postponeUrl, {target: item, swap: 'delete'});
        }
    }

    if (key === 'u') {
        var toast = document.getElementById('undo-toast');
        if (!toast) return;
        e.preventDefault();
        htmx.ajax('POST', list.dataset.undoUrl,
                  {target: document.body, swap: 'innerHTML',
                   values: {todo_ids: toast.dataset.todoIds, prev_status: toast.dataset.prevStatus}});
    }
});

htmx.onLoad(function(content) {
    initSortables(content);
    initTodoSwipe(content);
});
initSortables(document);
initTodoSwipe(document);
