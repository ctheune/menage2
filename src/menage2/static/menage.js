function initSortables(content) {
  var sortables = content.querySelectorAll(".sortable");
  for (var i = 0; i < sortables.length; i++) {
    var sortable = sortables[i];
    new Sortable(sortable, {
      animation: 150,
      filter: ".non-sortable", // 'filtered' class is not draggable
      ghostClass: "bg-blue-200",
    });
  }
}

// Full-screen image modal with prev/next navigation
var _modalImages = [];
var _modalIndex = 0;

function _modalUpdate() {
  var entry = _modalImages[_modalIndex];
  var img = document.getElementById("attachmentModalImage");
  if (img) {
    img.src = entry.full;
    img.alt = entry.alt;
  }
  var counter = document.getElementById("attachmentModalCounter");
  if (counter)
    counter.textContent =
      _modalImages.length > 1
        ? _modalIndex + 1 + " / " + _modalImages.length
        : "";
  var multi = _modalImages.length > 1;
  var prev = document.getElementById("attachmentModalPrev");
  var next = document.getElementById("attachmentModalNext");
  if (prev) prev.style.visibility = multi ? "visible" : "hidden";
  if (next) next.style.visibility = multi ? "visible" : "hidden";
}

function _modalNav(delta) {
  if (!_modalImages.length) return;
  _modalIndex =
    (_modalIndex + delta + _modalImages.length) % _modalImages.length;
  _modalUpdate();
}

document.addEventListener("click", function (e) {
  if (e.target.closest("#attachmentModalPrev")) {
    _modalNav(-1);
    return;
  }
  if (e.target.closest("#attachmentModalNext")) {
    _modalNav(1);
    return;
  }

  var thumb = e.target.closest(".todo-attachment-thumb");
  if (!thumb) return;
  e.stopPropagation();
  if (!thumb.dataset.fullUrl) return;
  var todoItem = thumb.closest(".todo-item");
  var all = todoItem
    ? Array.from(todoItem.querySelectorAll(".todo-attachment-thumb"))
    : [thumb];
  _modalImages = all.map(function (t) {
    return { full: t.dataset.fullUrl, alt: t.alt || "" };
  });
  _modalIndex = all.indexOf(thumb);
  if (_modalIndex < 0) _modalIndex = 0;
  _modalUpdate();
  var modalEl = document.getElementById("attachmentModal");
  if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
});

document.addEventListener("keydown", function (e) {
  var modal = document.getElementById("attachmentModal");
  if (!modal || !modal.classList.contains("show")) return;
  if (e.key === "ArrowLeft") {
    e.preventDefault();
    _modalNav(-1);
  }
  if (e.key === "ArrowRight") {
    e.preventDefault();
    _modalNav(1);
  }
});

// Upload attachments to a todo
function uploadAttachments(files, todoId) {
  if (!files || files.length === 0) return;

  var formData = new FormData();
  for (var i = 0; i < files.length; i++) {
    formData.append("files[]", files[i]);
  }

  return fetch("/todos/" + todoId + "/attachments", {
    method: "POST",
    body: formData,
    headers: { "X-Requested-With": "XMLHttpRequest" },
  }).then(function (r) {
    if (!r.ok)
      return r.text().then(function (msg) {
        throw new Error(msg || "Upload failed");
      });
    return r;
  });
}

document.body.addEventListener("showValidationError", function (e) {
  var existing = document.getElementById("error-toast");
  if (existing) existing.remove();

  var toast = document.createElement("div");
  toast.id = "error-toast";
  toast.style.cssText =
    "position:fixed;bottom:1.5rem;left:1.5rem;z-index:9999;background:#dc2626;color:#fff;padding:0.875rem 1.25rem;border-radius:0.75rem;box-shadow:0 8px 32px rgba(0,0,0,0.45);pointer-events:none;font-weight:600;";
  toast.textContent = (e.detail && e.detail.message) || "Validation error.";
  document.body.appendChild(toast);
  setTimeout(function () {
    toast.remove();
  }, 5000);
});

// Show error toast when todo text is empty (only tags entered)
document.body.addEventListener("showAddTodoError", function (e) {
  var existing = document.getElementById("error-toast");
  if (existing) existing.remove();

  var toast = document.createElement("div");
  toast.id = "error-toast";
  toast.style.cssText =
    "position:fixed;bottom:1.5rem;left:1.5rem;z-index:9999;background:#dc2626;color:#fff;padding:0.875rem 1.25rem;border-radius:0.75rem;box-shadow:0 8px 32px rgba(0,0,0,0.45);pointer-events:none;font-weight:600;";
  toast.textContent = "A todo needs text, not just tags.";
  document.body.appendChild(toast);
  setTimeout(function () {
    toast.remove();
  }, 5000);
});

var _undoTimer = null;
// Either path that requests an undo (toast click or 'u' shortcut) cancels the
// auto-dismiss timer so the toast stays put until showUndoConfirm replaces it.
document.body.addEventListener("undoRequested", function () {
  clearTimeout(_undoTimer);
});

// Show undo toast when server fires showUndoToast HX-Trigger event
document.body.addEventListener("showUndoToast", function (e) {
  var existing = document.getElementById("undo-toast");
  if (existing) existing.remove();
  clearTimeout(_undoTimer);

  var toast = document.createElement("div");
  toast.id = "undo-toast";
  toast.dataset.todoIds = e.detail.ids;
  toast.dataset.prevStatus = e.detail.prevStatus;
  toast.dataset.label = e.detail.label || "";
  toast.className = "undo-toast";
  toast.style.cssText =
    "background:#fef3c7;color:#78350f;border:1px solid #f59e0b;padding:0.875rem 1.25rem;border-radius:0.75rem;box-shadow:0 8px 32px rgba(0,0,0,0.2);cursor:pointer;font-weight:600;";
  toast.textContent =
    (e.detail.label || "Item") +
    " " +
    (e.detail.action || "completed") +
    ". (Undo)";

  toast.addEventListener("click", function () {
    htmx.trigger(document.body, "undoRequested");
  });

  document.body.appendChild(toast);
  _undoTimer = setTimeout(function () {
    toast.remove();
  }, 7000);
});

document.body.addEventListener("showUndoConfirm", function (e) {
  var toast = document.getElementById("undo-toast");
  if (!toast) return;
  var label = e.detail.label || "Item";
  toast.textContent = label + " uncompleted. UNDO OK.";
  toast.style.background = "#dcfce7";
  toast.style.color = "#14532d";
  toast.style.borderColor = "#16a34a";
  toast.style.cursor = "default";
  _undoTimer = setTimeout(function () {
    toast.remove();
  }, 2500);
});

document.addEventListener("keydown", function (e) {
  if (
    e.target.tagName === "INPUT" ||
    e.target.tagName === "TEXTAREA" ||
    e.target.contentEditable === "true"
  )
    return;

  if (e.key === "Escape") {
    var pane = document.getElementById("details-pane");
    if (
      pane &&
      !pane.classList.contains("d-none") &&
      !document.getElementById("protocol-run")
    ) {
      e.preventDefault();
      document
        .querySelectorAll("input.todo-checkbox:checked")
        .forEach(function (cb) {
          cb.checked = false;
        });
      closeDetailsPane();
      return;
    }
  }

  // [ / ] / u are wired via hyperscript on the batch form in list_todos.pt.
  // c / P / h / a are wired via hyperscript on the batch-menu buttons there.
  // d / f / s / ~ / @ / l field shortcuts are wired via hyperscript in
  // _todo_details_panel.pt.
  // The repetition history panel is pure htmx: see the .todo-recurrence button
  // in _todo_groups.pt and _recurrence_history.pt.
});

// --- Keyboard shortcut help overlay ---
// HTMX swaps body content frequently and removes any element previously
// appended to <body>. We therefore (a) keep `_helpOverlay` as a singleton we
// can re-attach on every load and (b) bind the keydown handler exactly once
// against `document`, which is never replaced.
var _helpOverlay = null;

function _kbdSection(title) {
  return (
    '<p class="text-uppercase fw-semibold text-secondary mb-1 mt-3 small">' +
    title +
    "</p>"
  );
}

function _kbdRow(key, desc) {
  return (
    '<tr class="small">' +
    '<td class="pe-3 text-nowrap align-top pb-1"><kbd>' +
    key +
    "</kbd></td>" +
    '<td class="align-top pb-1 text-body">' +
    desc +
    "</td>" +
    "</tr>"
  );
}

function _kbdCol(sections) {
  return '<div class="col">' + sections.join("") + "</div>";
}

function ensureHelpOverlay() {
  if (_helpOverlay && document.body.contains(_helpOverlay)) return _helpOverlay;
  _helpOverlay = document.createElement("div");
  _helpOverlay.id = "kbd-help-overlay";
  _helpOverlay.className =
    "position-fixed top-0 start-0 w-100 h-100 align-items-center justify-content-center";
  _helpOverlay.style.cssText =
    "display:none;background:rgba(0,0,0,0.45);z-index:9999;";
  var col1 = _kbdCol([
    _kbdSection("Everywhere"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("?", "Show this help"),
    _kbdRow("Esc", "Cancel / close"),
    "</tbody></table>",

    _kbdSection("Todo list"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("click", "Select item \u2014 opens details pane"),
    _kbdRow("c", "Mark selected done"),
    _kbdRow("h", "Put selected on hold"),
    _kbdRow("a", "Activate selected (on-hold / done list)"),
    _kbdRow("Shift+P", "Postpone selected by 1 day"),
    _kbdRow("[", "Collapse all groups"),
    _kbdRow("]", "Expand all groups"),
    _kbdRow("click group", "Collapse / expand that group"),
    _kbdRow("u", "Undo last action"),
    _kbdRow("click \u21bb", "Show repetition history"),
    "</tbody></table>",

    _kbdSection("Details pane"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("e", "Edit title"),
    _kbdRow("d", "Edit due date"),
    _kbdRow("f", "Edit repetition rule"),
    _kbdRow("s", "Edit tags"),
    _kbdRow("~", "Edit note"),
    _kbdRow("@", "Edit assignees"),
    _kbdRow("l", "Add / edit link"),
    _kbdRow("click field", "Edit that field"),
    _kbdRow("Esc", "Close pane / picker"),
    "</tbody></table>",
  ]);
  var col2 = _kbdCol([
    _kbdSection("Protocol run (in details pane)"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("j / \u2193", "Next item"),
    _kbdRow("k / \u2191", "Previous item"),
    _kbdRow("c", "Mark current done"),
    _kbdRow("t", "Send current to the todo list"),
    _kbdRow("e", "Edit current item before sending"),
    _kbdRow("Esc", "Close details pane"),
    "</tbody></table>",

    _kbdSection("Adding a todo (and protocol items)"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("#tag", "Attach a tag (single word)"),
    _kbdRow("@who", "Assign to a person or team"),
    _kbdRow("^when", "Due date \u2014 <kbd>^tomorrow</kbd>, <kbd>^next week</kbd>"),
    _kbdRow("*rule", "Repetition \u2014 <kbd>*every week</kbd>"),
    _kbdRow("~text", "Note (runs to the next marker)"),
    _kbdRow("[label](url)", "Link"),
    _kbdRow("~[…]", "Brackets hold anything \u2014 <kbd>~[costs 5 # each]</kbd>"),
    _kbdRow("\\#", "Backslash writes a marker as plain text"),
    "</tbody></table>",

    _kbdSection("Protocol editor"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("click line", "Edit that line as text"),
    _kbdRow("Enter", "Save the line"),
    _kbdRow("Esc", "Cancel the edit"),
    "</tbody></table>",
  ]);
  _helpOverlay.innerHTML =
    '<div class="card shadow-lg" style="max-width:42rem;width:90%;max-height:90vh;overflow-y:auto;">' +
    '<div class="card-body p-4">' +
    '<h6 class="text-uppercase fw-bold text-secondary small mb-3 mt-0">Keyboard shortcuts</h6>' +
    '<div class="row g-0">' +
    col1 +
    col2 +
    "</div>" +
    "</div></div>";
  document.body.appendChild(_helpOverlay);
  _helpOverlay.addEventListener("click", function (e) {
    if (e.target === _helpOverlay) hideHelp();
  });
  return _helpOverlay;
}

function showHelp() {
  var o = ensureHelpOverlay();
  o.style.display = "flex";
}

function hideHelp() {
  if (_helpOverlay) _helpOverlay.style.display = "none";
}

document.addEventListener("keydown", function (e) {
  if (e.key === "?") {
    var tag = document.activeElement
      ? document.activeElement.tagName.toLowerCase()
      : "";
    if (
      tag === "input" ||
      tag === "textarea" ||
      tag === "select" ||
      (document.activeElement && document.activeElement.isContentEditable)
    )
      return;
    e.preventDefault();
    showHelp();
    return;
  }
  if (
    e.key === "Escape" &&
    _helpOverlay &&
    _helpOverlay.style.display === "flex"
  ) {
    e.preventDefault();
    hideHelp();
  }
});

// --- Details pane -----------------------------------------------------------

var _detailsItemId = null;

function closeDetailsPane() {
  var pane = document.getElementById("details-pane");
  var panel = document.getElementById("details-panel");
  if (pane) pane.classList.add("d-none");
  if (panel) panel.innerHTML = "";
  _detailsItemId = null;
  var bd = document.getElementById("run-panel-backdrop");
  if (bd) bd.parentNode.removeChild(bd);
}

// Keep as alias so templates that still reference closeRunPanel work.
function closeRunPanel() {
  closeDetailsPane();
}

// Details pane close button
document.addEventListener("click", function (e) {
  if (!e.target.closest(".details-close-btn")) return;
  document
    .querySelectorAll("input.todo-checkbox:checked")
    .forEach(function (cb) {
      cb.checked = false;
    });
  closeDetailsPane();
});

// "Start run now" button
document.addEventListener("click", function (e) {
  var btn = e.target.closest(".details-start-run");
  if (!btn) return;
  e.preventDefault();
  var panelUrl = btn.dataset.panelUrl;
  if (!panelUrl) return;
  var runContent = btn.closest(".details-run-content");
  if (runContent)
    runContent.innerHTML = '<div class="p-2 text-muted small">Loading…</div>';
  fetch(panelUrl + "?inline=1")
    .then(function (r) {
      return r.text();
    })
    .then(function (html) {
      if (runContent && runContent.isConnected) {
        runContent.innerHTML = html;
        htmx.process(runContent);
        _runCurrentIdx = 0;
        _runHighlight();
      }
    });
});

// --- Protocol run page interactions ----------------------------------------
//
// The run-item actions (done / send / edit) are plain htmx on the buttons in
// _protocol_run_partial.pt: done and send post and swap the whole section, and
// edit reveals that row's inline form via hyperscript. Only the j/k cursor and
// the hotkeys that click those buttons live here.

// --- Run-item navigation + hotkeys ---
var _runCurrentIdx = 0;

function _runItems() {
  return Array.from(document.querySelectorAll(".protocol-run-item"));
}
function _runHighlight() {
  var items = _runItems();
  items.forEach(function (el, i) {
    el.classList.toggle("is-current", i === _runCurrentIdx);
  });
  var current = items[_runCurrentIdx];
  if (current) current.scrollIntoView({ block: "nearest", behavior: "smooth" });
}
function _runMove(delta) {
  var items = _runItems();
  if (!items.length) return;
  _runCurrentIdx = Math.max(
    0,
    Math.min(items.length - 1, _runCurrentIdx + delta),
  );
  _runHighlight();
}
function _runFire(action) {
  var items = _runItems();
  var current = items[_runCurrentIdx];
  if (!current) return;
  var btn = current.querySelector(
    '.protocol-run-action[data-action="' + action + '"]',
  );
  if (btn) btn.click();
}

document.addEventListener("keydown", function (e) {
  if (!document.getElementById("protocol-run")) return;
  if (
    e.target.tagName === "INPUT" ||
    e.target.tagName === "TEXTAREA" ||
    e.target.contentEditable === "true"
  )
    return;
  if (e.key === "j" || e.key === "ArrowDown") {
    e.preventDefault();
    _runMove(1);
  } else if (e.key === "k" || e.key === "ArrowUp") {
    e.preventDefault();
    _runMove(-1);
  } else if (e.key === "c") {
    e.preventDefault();
    _runFire("done");
  } else if (e.key === "t") {
    e.preventDefault();
    _runFire("send");
  } else if (e.key === "e") {
    e.preventDefault();
    _runFire("edit");
  } else if (e.key === "Escape") {
    e.preventDefault();
    var pane = document.getElementById("details-pane");
    if (pane && !pane.classList.contains("d-none")) {
      document
        .querySelectorAll("input.todo-checkbox:checked")
        .forEach(function (cb) {
          cb.checked = false;
        });
      closeDetailsPane();
    } else {
      var run = document.getElementById("protocol-run");
      if (run && run.dataset.todoRoute) location.href = run.dataset.todoRoute;
    }
  }
});


// --- Bootstrapping ----------------------------------------------------------
//
// Protocol titles and items are edited with plain inputs and a view/edit
// toggle written in hyperscript (protocols/edit.pt, _protocol_item.pt), so
// there is nothing left to initialise for them here.

htmx.onLoad(function (content) {
  ensureHelpOverlay();
  initSortables(content);
  if (document.getElementById("protocol-run")) _runHighlight();
});
ensureHelpOverlay();
initSortables(document);
if (document.getElementById("protocol-run")) _runHighlight();

function isCaretAtStart(element) {
  // Works only in contentEditable with plaintext-only
  const selection = window.getSelection();
  if (!selection.rangeCount) return false;

  const range = selection.getRangeAt(0);
  return range.collapsed && range.startOffset === 0;
}
