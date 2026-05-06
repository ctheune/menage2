function isGroupCollapsed(tag) {
  if (!tag) return false;
  var header = document.querySelector(
    '.tag-group-header[data-tag="' + tag + '"]',
  );
  if (header && header.dataset.open === "false") return true;
  var colon = tag.lastIndexOf(":");
  if (colon > -1) return isGroupCollapsed(tag.slice(0, colon));
  return false;
}

function applyGroupVisibility() {
  document.querySelectorAll("[data-parent-tag]").forEach(function (el) {
    el.style.display = isGroupCollapsed(el.dataset.parentTag) ? "none" : "";
  });
}

function toggleGroup(tag) {
  var header = document.querySelector(
    '.tag-group-header[data-tag="' + tag + '"]',
  );
  if (!header) return;
  header.dataset.open = header.dataset.open === "false" ? "true" : "false";
  applyGroupVisibility();
}

function setAllGroups(open) {
  document.querySelectorAll(".tag-group-header").forEach(function (h) {
    h.dataset.open = open ? "true" : "false";
  });
  applyGroupVisibility();
}

document.addEventListener("click", function (e) {
  var header = e.target.closest(".tag-group-header");
  if (header) toggleGroup(header.dataset.tag);
});

function swipePost(url, todoId, list) {
  // The done/hold endpoints respond with empty body + HX-Trigger
  // (todo-updated reloads #todo-list); the swipe transform animates while
  // the request is in flight.
  htmx.ajax("POST", url, {
    target: list,
    swap: "none",
    values: { todo_ids: todoId },
  });
}

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

var _swipeTouchState = new WeakMap();
var _SWIPE_THRESHOLD = 80;

document.addEventListener(
  "touchstart",
  function (e) {
    var item = e.target.closest(".todo-item");
    if (!item) return;
    var inner = item.querySelector(".todo-content");
    if (!inner) return;
    inner.style.transition = "none";
    _swipeTouchState.set(item, { startX: e.touches[0].clientX, dx: 0 });
  },
  { passive: true },
);

document.addEventListener(
  "touchmove",
  function (e) {
    var item = e.target.closest(".todo-item");
    if (!item) return;
    var state = _swipeTouchState.get(item);
    if (!state) return;
    var inner = item.querySelector(".todo-content");
    if (!inner) return;
    state.dx = e.touches[0].clientX - state.startX;
    inner.style.transform =
      "translateX(" + Math.max(-150, Math.min(150, state.dx)) + "px)";
    item.dataset.swipeDir = state.dx > 0 ? "right" : state.dx < 0 ? "left" : "";
  },
  { passive: true },
);

document.addEventListener("touchend", function (e) {
  var item = e.target.closest(".todo-item");

  if (!item) return;
  var state = _swipeTouchState.get(item);
  if (!state) return;
  _swipeTouchState.delete(item);
  var inner = item.querySelector(".todo-content");
  if (!inner) return;
  inner.style.transition = "transform 0.2s ease";
  var dx = state.dx;
  var list = document.getElementById("todo-list");
  var checkbox = item.querySelector(".todo-checkbox");
  var todoId = checkbox ? checkbox.value : null;
  if (dx >= _SWIPE_THRESHOLD && list && todoId) {
    inner.style.transform = "translateX(100vw)";
    swipePost(list.dataset.doneUrl, todoId, list);
  } else if (dx <= -_SWIPE_THRESHOLD && list && todoId) {
    inner.style.transform = "translateX(-100vw)";
    swipePost(list.dataset.holdUrl, todoId, list);
  } else {
    inner.style.transform = "translateX(0)";
    delete item.dataset.swipeDir;
  }
});

function initTodoSwipe() {} // kept for htmx.onLoad call below; delegation handles all items

// parseTagsFromRaw and fetch helpers live in composite-input.js

// Delegated handler: clicking a todo-item row toggles its checkbox
document.addEventListener("click", function (e) {
  var item = e.target.closest(".todo-item");
  if (!item) return;
  var checkbox = item.querySelector(".todo-checkbox");
  if (!checkbox || e.target === checkbox) return;
  if (
    e.target.closest("a") ||
    e.target.closest("button") ||
    e.target.closest("img")
  )
    return;
  checkbox.checked = !checkbox.checked;
  checkbox.dispatchEvent(new Event("change", { bubbles: true }));
});

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

// Drag-and-drop image upload onto todo list items
document.addEventListener("dragover", function (e) {
  if (e.target.closest("#todo-form")) return;
  var item = e.target.closest(".todo-item");
  if (!item) return;
  e.preventDefault();
  item.classList.add("todo-item--drag-over");
});

document.addEventListener("dragleave", function (e) {
  var item = e.target.closest(".todo-item");
  if (!item) return;
  if (!item.contains(e.relatedTarget)) {
    item.classList.remove("todo-item--drag-over");
  }
});

document.addEventListener("drop", function (e) {
  if (e.target.closest("#todo-form")) return;
  var item = e.target.closest(".todo-item");
  if (!item) return;
  e.preventDefault();
  item.classList.remove("todo-item--drag-over");

  var files = e.dataTransfer && e.dataTransfer.files;
  if (!files || files.length === 0) return;

  var todoId = item.id.replace("todo-", "");
  if (!todoId) return;

  var formData = new FormData();
  for (var i = 0; i < files.length; i++) {
    formData.append("files[]", files[i]);
  }

  item.classList.add("todo-item--uploading");

  fetch("/todos/" + todoId + "/attachments", {
    method: "POST",
    body: formData,
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then(function (r) {
      if (!r.ok)
        return r.text().then(function (msg) {
          throw new Error(msg || "Upload failed");
        });
      return r.text();
    })
    .then(function (html) {
      item.classList.remove("todo-item--uploading");
      var tmp = document.createElement("template");
      tmp.innerHTML = html.trim();
      var newItem = tmp.content.firstElementChild;
      if (newItem) item.replaceWith(newItem);
    })
    .catch(function (err) {
      item.classList.remove("todo-item--uploading");
      console.error("Attachment upload failed:", err);
      var alert = document.createElement("div");
      alert.className =
        "alert alert-danger alert-dismissible py-1 px-2 small mt-1 mb-0";
      alert.setAttribute("role", "alert");
      alert.textContent = err.message;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn-close btn-sm";
      btn.setAttribute("data-bs-dismiss", "alert");
      btn.setAttribute("aria-label", "Close");
      alert.appendChild(btn);
      item.after(alert);
      setTimeout(function () {
        if (alert.parentNode) alert.remove();
      }, 6000);
    });
});

function initTagInput() {
  var container = document.getElementById("todo-tag-input");
  if (!container) return;
  var form = document.getElementById("todo-form");
  if (!form) return;

  var ci = CompositeInput(container, {
    textOuter: document.getElementById("todo-text"),
    hiddenInput: document.getElementById("todo-hidden-text"),
    quickPickEl: document.getElementById("todo-quick-pick"),
    quickPickUrl: "/todos/top-tags.json",
    form: form,
    tags: true,
    note: true,
    recurrence: true,
    dueDate: true,
    assignees: true,
    links: true,
    sessionKey: "todo-tags",
    placeholder: "New todo\u2026",
    principalsUrl: "/todos/principals.json",
  });
  if (!ci) return;

  var _pendingText = null;

  form.addEventListener(
    "submit",
    function () {
      _pendingText = ci.buildCompositeText();
      ci.clearVolatileState();
      sessionStorage.setItem("todo-add-focus", "1");
    },
    true,
  );

  form.addEventListener("htmx:configRequest", function (e) {
    if (_pendingText !== null) {
      e.detail.parameters["text"] = _pendingText;
      _pendingText = null;
    }
    var removed = ci.getRemovedAttachments();
    if (removed.length) {
      e.detail.parameters["remove_attachments"] = removed.join(",");
    }
  });

  document.body.addEventListener(
    "showAddTodoError",
    function (e) {
      ci.restoreFromRaw(e.detail.input || "");
    },
    true,
  );

  if (sessionStorage.getItem("todo-add-focus")) {
    sessionStorage.removeItem("todo-add-focus");
    setTimeout(function () {
      ci.focusFirst();
    }, 0);
  }
}

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

function _firstCheckedItem() {
  var box = document.querySelector("input.todo-checkbox:checked");
  return box ? box.closest(".todo-item") : null;
}

document.addEventListener("keydown", function (e) {
  if (
    e.target.tagName === "INPUT" ||
    e.target.tagName === "TEXTAREA" ||
    e.target.contentEditable === "true"
  )
    return;

  if (e.key === "Escape") {
    if (document.querySelector(".todo-popover")) {
      e.preventDefault();
      closePopovers();
      return;
    }
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

  // r / [ / ] / u are wired via hyperscript on #done-list and #todo-list.
  // c / p / P / h are wired via hyperscript on the form in _todo_groups.pt.
  // d / f / s / ~ / @ / l field shortcuts are wired via hyperscript in
  // _todo_details_panel.pt.
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
  return (
    d.getFullYear() +
    "-" +
    String(d.getMonth() + 1).padStart(2, "0") +
    "-" +
    String(d.getDate()).padStart(2, "0")
  );
}

function _addDays(d, n) {
  var x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function _quickOptions() {
  var t = new Date();
  var weekdayShort = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var opts = [
    { label: "Today", iso: _isoDate(t) },
    { label: "Tomorrow", iso: _isoDate(_addDays(t, 1)) },
  ];
  for (var i = 2; i <= 4; i++) {
    var d = _addDays(t, i);
    opts.push({ label: weekdayShort[d.getDay()], iso: _isoDate(d) });
  }
  opts.push({ label: "+1 week", iso: _isoDate(_addDays(t, 7)) });
  opts.push({ label: "No date", iso: null });
  return opts;
}

function openPicker(opts) {
  closePopovers();
  var pop = document.createElement("div");
  pop.className = "todo-popover";
  pop.dataset.role = opts.role || "date-picker";

  if (opts.title) {
    var h = document.createElement("div");
    h.style.cssText =
      "font-size:0.75rem;font-weight:600;color:var(--bs-secondary-color);margin-bottom:0.35rem;";
    h.textContent = opts.title;
    pop.appendChild(h);
  }

  // --- Quick chips row ---
  var chips = document.createElement("div");
  chips.className = "todo-popover-actions";
  chips.style.marginTop = "0";
  pop.appendChild(chips);

  // --- Custom text input + live preview ---
  var input = document.createElement("input");
  input.type = "text";
  input.placeholder = "tomorrow / next wed / 2026-05-12 \u2026";
  input.value = opts.initialISO || "";
  pop.appendChild(input);

  var preview = document.createElement("div");
  preview.className = "todo-popover-preview";
  pop.appendChild(preview);

  // --- Calendar ---
  var cal = document.createElement("div");
  pop.appendChild(cal);

  // --- Footer actions ---
  var footer = document.createElement("div");
  footer.className = "todo-popover-actions";
  var setBtn = document.createElement("button");
  setBtn.type = "button";
  setBtn.textContent = opts.commitLabel || "Set";
  var cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.textContent = "Cancel";
  footer.appendChild(setBtn);
  footer.appendChild(cancelBtn);
  pop.appendChild(footer);

  anchorPopover(pop, opts.anchorEl);

  // --- State ---
  var pendingISO = opts.initialISO || null;
  var pendingMonth = pendingISO
    ? new Date(pendingISO + "T00:00:00")
    : new Date();
  pendingMonth.setDate(1);

  function commit(iso) {
    if (typeof opts.onCommit === "function") opts.onCommit(iso);
    closePopovers();
  }

  function cancel() {
    if (typeof opts.onCancel === "function") opts.onCancel();
    closePopovers();
  }

  // --- Render quick chips ---
  _quickOptions().forEach(function (opt) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = opt.label;
    btn.addEventListener("click", function () {
      commit(opt.iso);
    });
    chips.appendChild(btn);
  });

  // --- Render calendar ---
  function renderCalendar() {
    cal.innerHTML = "";

    var nav = document.createElement("div");
    nav.style.cssText =
      "display:flex;justify-content:space-between;align-items:center;font-size:0.75rem;font-weight:600;color:var(--bs-secondary-color);margin:0.25rem 0;";
    var prev = document.createElement("button");
    prev.type = "button";
    prev.textContent = "\u2039";
    prev.style.cssText =
      "background:none;border:none;cursor:pointer;font-size:1rem;color:inherit;padding:0 0.5rem;";
    prev.addEventListener("click", function () {
      pendingMonth.setMonth(pendingMonth.getMonth() - 1);
      renderCalendar();
    });
    var next = document.createElement("button");
    next.type = "button";
    next.textContent = "\u203a";
    next.style.cssText = prev.style.cssText;
    next.addEventListener("click", function () {
      pendingMonth.setMonth(pendingMonth.getMonth() + 1);
      renderCalendar();
    });
    var navLabel = document.createElement("span");
    navLabel.textContent = pendingMonth.toLocaleDateString(undefined, {
      month: "long",
      year: "numeric",
    });
    nav.appendChild(prev);
    nav.appendChild(navLabel);
    nav.appendChild(next);
    cal.appendChild(nav);

    var grid = document.createElement("div");
    grid.className = "todo-mini-cal";
    ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].forEach(function (d) {
      var hCell = document.createElement("div");
      hCell.className = "todo-mini-cal-cell todo-mini-cal-header";
      hCell.textContent = d;
      grid.appendChild(hCell);
    });

    var first = new Date(pendingMonth);
    first.setDate(1);
    var startWeekday = (first.getDay() + 6) % 7; // Mon=0
    var daysInMonth = new Date(
      first.getFullYear(),
      first.getMonth() + 1,
      0,
    ).getDate();
    var todayISO = _isoDate(new Date());

    for (var i = 0; i < startWeekday; i++) {
      var blank = document.createElement("div");
      blank.className = "todo-mini-cal-cell muted";
      grid.appendChild(blank);
    }
    for (var d = 1; d <= daysInMonth; d++) {
      var cell = document.createElement("div");
      cell.className = "todo-mini-cal-cell";
      cell.textContent = d;
      var iso = _isoDate(new Date(first.getFullYear(), first.getMonth(), d));
      if (iso === todayISO) cell.classList.add("today");
      if (iso === pendingISO) cell.classList.add("selected");
      cell.addEventListener(
        "click",
        (function (iso) {
          return function () {
            commit(iso);
          };
        })(iso),
      );
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
      preview.textContent = "";
      preview.classList.remove("todo-popover-preview--invalid");
      pendingISO = null;
      return;
    }
    previewTimer = setTimeout(function () {
      fetch("/todos/parse-date?q=" + encodeURIComponent(q))
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (data.ok) {
            pendingISO = data.date;
            preview.textContent =
              "\u2192 " + data.label + " (" + data.date + ")";
            preview.classList.remove("todo-popover-preview--invalid");
            // Re-render calendar to month containing the new date
            var newMonth = new Date(data.date + "T00:00:00");
            if (
              newMonth.getMonth() !== pendingMonth.getMonth() ||
              newMonth.getFullYear() !== pendingMonth.getFullYear()
            ) {
              pendingMonth = newMonth;
              pendingMonth.setDate(1);
            }
            renderCalendar();
          } else {
            pendingISO = null;
            preview.textContent = "? cannot parse";
            preview.classList.add("todo-popover-preview--invalid");
          }
        })
        .catch(function () {});
    }, 120);
  }

  input.addEventListener("input", updatePreview);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      commit(pendingISO);
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    }
  });
  setBtn.addEventListener("click", function () {
    commit(pendingISO);
  });
  cancelBtn.addEventListener("click", cancel);

  renderCalendar();
  if (opts.initialISO) updatePreview();
  setTimeout(function () {
    input.focus();
    input.select();
  }, 0);
  return pop;
}

// Simple note-text popover. opts: {anchorEl, initialNote, title, onCommit, onCancel}
function openNotePicker(opts) {
  closePopovers();
  var pop = document.createElement("div");
  pop.className = "todo-popover todo-note-popover";
  pop.style.cssText =
    "position:absolute;z-index:1060;background:#fff;border:1px solid #dee2e6;border-radius:.5rem;padding:1rem;box-shadow:0 4px 20px rgba(0,0,0,.15);width:18rem;";
  var safeInitial = (opts.initialNote || "").replace(/"/g, "&quot;");
  pop.innerHTML =
    '<label style="font-size:.85rem;font-weight:600;display:block;margin-bottom:.5rem">' +
    (opts.title || "Note") +
    "</label>" +
    '<input type="text" class="form-control form-control-sm" placeholder="Note text\u2026" value="' +
    safeInitial +
    '"/>' +
    '<div class="d-flex gap-2 mt-2 justify-content-end">' +
    '<button type="button" class="btn btn-sm btn-link text-muted">Cancel</button>' +
    '<button type="button" class="btn btn-sm btn-dark">Set</button>' +
    "</div>";
  anchorPopover(pop, opts.anchorEl);
  var input = pop.querySelector("input");
  var setBtn = pop.querySelector(".btn-dark");
  var cancelBtn = pop.querySelector(".btn-link");
  function commit() {
    var val = input.value.trim();
    closePopovers();
    if (opts.onCommit) opts.onCommit(val);
  }
  function cancel() {
    closePopovers();
    if (opts.onCancel) opts.onCancel();
  }
  setBtn.addEventListener("click", commit);
  cancelBtn.addEventListener("click", cancel);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    }
    if (e.key === "Escape") {
      cancel();
    }
  });
  setTimeout(function () {
    input.focus();
    input.select();
  }, 0);
}

// Two-field link popover. opts: {anchorEl, initialLink, onCommit, onCancel}
function openLinkPicker(opts) {
  closePopovers();
  var pop = document.createElement("div");
  pop.className = "todo-popover todo-link-popover";
  pop.style.cssText =
    "position:absolute;z-index:1060;background:#fff;border:1px solid #dee2e6;border-radius:.5rem;padding:1rem;box-shadow:0 4px 20px rgba(0,0,0,.15);width:20rem;";
  var m = (opts.initialLink || "").match(
    /^\[([^\]]*)\]\(([a-zA-Z][a-zA-Z0-9+\-.]*:\/\/[^)]+)\)$/,
  );
  var initUrl = m ? m[2] : "";
  var initLabel = m ? m[1] : "";
  var safeUrl = initUrl.replace(/"/g, "&quot;");
  var safeLabel = initLabel.replace(/"/g, "&quot;");
  pop.innerHTML =
    '<label style="font-size:.85rem;font-weight:600;display:block;margin-bottom:.5rem">URL</label>' +
    '<input class="form-control form-control-sm mb-2" placeholder="https://… or obsidian://…" value="' +
    safeUrl +
    '"/>' +
    '<label style="font-size:.85rem;font-weight:600;display:block;margin-bottom:.5rem">Label <span style="font-weight:400;color:#6c757d">(optional)</span></label>' +
    '<input class="form-control form-control-sm" placeholder="Link text…" value="' +
    safeLabel +
    '"/>' +
    '<div class="d-flex gap-2 mt-2 justify-content-end">' +
    '<button type="button" class="btn btn-sm btn-link text-muted">Cancel</button>' +
    '<button type="button" class="btn btn-sm btn-dark">Set</button>' +
    "</div>";
  anchorPopover(pop, opts.anchorEl);
  var urlInput = pop.querySelectorAll("input")[0];
  var labelInput = pop.querySelectorAll("input")[1];
  var setBtn = pop.querySelector(".btn-dark");
  var cancelBtn = pop.querySelector(".btn-link");
  function commit() {
    var url = urlInput.value.trim();
    var label = labelInput.value.trim();
    if (!url) {
      urlInput.classList.add("is-invalid");
      urlInput.focus();
      return;
    }
    if (!url.match(/^[a-zA-Z][a-zA-Z0-9+\-.]*:\/\//)) url = "http://" + url;
    closePopovers();
    if (opts.onCommit) opts.onCommit("[" + label + "](" + url + ")");
  }
  function cancel() {
    closePopovers();
    if (opts.onCancel) opts.onCancel();
  }
  setBtn.addEventListener("click", commit);
  cancelBtn.addEventListener("click", cancel);
  [urlInput, labelInput].forEach(function (inp) {
    inp.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        commit();
      }
      if (e.key === "Escape") cancel();
    });
  });
  setTimeout(function () {
    urlInput.focus();
  }, 0);
}

// Anchor a popover element below `anchorEl`. Removes any existing popovers first.
function anchorPopover(pop, anchorEl) {
  document.body.appendChild(pop);
  var rect = anchorEl
    ? anchorEl.getBoundingClientRect()
    : { top: 100, left: 100, bottom: 100, right: 100 };
  var top = window.scrollY + rect.bottom + 4;
  var left = window.scrollX + Math.min(rect.left, window.innerWidth - 320);
  pop.style.top = top + "px";
  pop.style.left = Math.max(8, left) + "px";
}

function closePopovers() {
  document.querySelectorAll(".todo-popover").forEach(function (el) {
    el.remove();
  });
}

// Click-outside closes any open popover.
document.addEventListener("mousedown", function (e) {
  if (e.target.closest(".todo-popover")) return;
  if (e.target.closest(".todo-due")) return;
  if (e.target.closest(".todo-date-pill")) return;
  closePopovers();
});

// --- Helpers wrapping openPicker for specific contexts ---

function openSetDuePicker(itemEl, anchorEl) {
  openPicker({
    anchorEl: anchorEl || itemEl,
    initialISO: _readDueFromDetailsPanel() || itemEl.dataset.dueDate || null,
    title: "Due date",
    onCommit: function (iso) {
      _renderDueIntoDetailsPanel(iso || "");
    },
  });
}

function openPostponePicker(itemEl, ids) {
  var list = document.getElementById("todo-list");
  if (!list) return;
  var trigger = list.querySelector(".postpone-trigger");
  if (!trigger) return;
  openPicker({
    anchorEl: itemEl,
    title: "Postpone\u2026",
    role: "postpone-palette",
    onCommit: function (iso) {
      // Set a transient due_date hidden input on the trigger button so the
      // form-driven hx-post serialises it. Cleaned up after dispatch.
      var existing = trigger.parentNode.querySelector(
        'input[name="due_date"][data-postpone-transient]',
      );
      if (existing) existing.remove();
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "due_date";
      hidden.value = iso || "";
      hidden.dataset.postponeTransient = "true";
      trigger.parentNode.insertBefore(hidden, trigger);
      htmx.trigger(trigger, "postponeSelected");
      // Remove after htmx has serialised the form (it does so synchronously
      // inside the trigger handler, but defer to be safe).
      setTimeout(function () {
        if (hidden.parentNode) hidden.remove();
      }, 0);
    },
  });
}

function openPostponePickerForSelection() {
  var box = document.querySelector("input.todo-checkbox:checked");
  if (!box) return;
  var anchor = box.closest(".todo-item") || box;
  var ids = Array.from(document.querySelectorAll("input.todo-checkbox:checked"))
    .map(function (b) {
      return b.dataset.id;
    })
    .join(",");
  openPostponePicker(anchor, ids);
}

// Click on the due-date chip opens the set-due picker for that row.
document.addEventListener("click", function (e) {
  var chip = e.target.closest(".todo-due");
  if (!chip) return;
  var item = chip.closest(".todo-item");
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
  "every day",
  "every week",
  "every month",
  "every year",
  "after a day",
  "after a week",
  "after a month",
  "after a year",
];

function openRecurrencePicker(opts) {
  closePopovers();
  var pop = document.createElement("div");
  pop.className = "todo-popover";
  pop.dataset.role = opts.role || "recurrence-picker";

  if (opts.title) {
    var h = document.createElement("div");
    h.style.cssText =
      "font-size:0.75rem;font-weight:600;color:var(--bs-secondary-color);margin-bottom:0.35rem;";
    h.textContent = opts.title;
    pop.appendChild(h);
  }

  var chips = document.createElement("div");
  chips.className = "todo-popover-actions";
  chips.style.marginTop = "0";
  pop.appendChild(chips);

  var input = document.createElement("input");
  input.type = "text";
  input.placeholder = "every wednesday / after 10 days / every 15th \u2026";
  input.value = opts.initialLabel || "";
  pop.appendChild(input);

  var preview = document.createElement("div");
  preview.className = "todo-popover-preview";
  pop.appendChild(preview);

  var footer = document.createElement("div");
  footer.className = "todo-popover-actions";
  var setBtn = document.createElement("button");
  setBtn.type = "button";
  setBtn.textContent = opts.commitLabel || "Set";
  var clearBtn = document.createElement("button");
  clearBtn.type = "button";
  clearBtn.textContent = "No repeat";
  var cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.textContent = "Cancel";
  footer.appendChild(setBtn);
  footer.appendChild(clearBtn);
  footer.appendChild(cancelBtn);
  pop.appendChild(footer);

  anchorPopover(pop, opts.anchorEl);

  var pendingLabel = opts.initialLabel || null;

  function commit(label) {
    if (typeof opts.onCommit === "function") opts.onCommit(label || null);
    closePopovers();
  }
  function cancel() {
    if (typeof opts.onCancel === "function") opts.onCancel();
    closePopovers();
  }

  _RECURRENCE_CHIPS.forEach(function (label) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.addEventListener("click", function () {
      commit(label);
    });
    chips.appendChild(btn);
  });

  var previewTimer = null;
  function updatePreview() {
    clearTimeout(previewTimer);
    var q = input.value.trim();
    if (!q) {
      preview.textContent = "";
      preview.classList.remove("todo-popover-preview--invalid");
      pendingLabel = null;
      return;
    }
    previewTimer = setTimeout(function () {
      fetch("/todos/parse-recurrence?q=" + encodeURIComponent(q))
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (data.ok) {
            pendingLabel = data.label;
            preview.textContent = "\u21bb " + data.label;
            preview.classList.remove("todo-popover-preview--invalid");
          } else {
            pendingLabel = null;
            preview.textContent = "? cannot parse";
            preview.classList.add("todo-popover-preview--invalid");
          }
        })
        .catch(function () {});
    }, 120);
  }
  input.addEventListener("input", updatePreview);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      commit(pendingLabel);
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    }
  });
  setBtn.addEventListener("click", function () {
    commit(pendingLabel);
  });
  clearBtn.addEventListener("click", function () {
    commit(null);
  });
  cancelBtn.addEventListener("click", cancel);

  if (opts.initialLabel) updatePreview();
  setTimeout(function () {
    input.focus();
    input.select();
  }, 0);
  return pop;
}

function openSetRecurrencePicker(itemEl, anchorEl) {
  openRecurrencePicker({
    anchorEl: anchorEl || itemEl,
    initialLabel:
      _readRecurrenceLabelFromDetailsPanel() ||
      itemEl.dataset.recurrence ||
      null,
    title: "Repeat",
    onCommit: function (label) {
      if (!label) {
        _renderRecurrenceIntoDetailsPanel(null, null);
        return;
      }
      fetch("/todos/parse-recurrence?q=" + encodeURIComponent(label))
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (!data.ok) return;
          _renderRecurrenceIntoDetailsPanel(
            {
              kind: data.kind,
              interval_value: data.interval_value,
              interval_unit: data.interval_unit,
              weekday: data.weekday,
              month_day: data.month_day,
            },
            data.label,
          );
        });
    },
  });
}

// --- Generic item picker (shared by tags + assignees) ------------------------

function _openItemsPicker(opts) {
  // opts.anchorEl, opts.title, opts.items[], opts.placeholder,
  // opts.prefix, opts.suggestUrl, opts.suggestTransform, opts.onCommit
  closePopovers();
  var itemSet = (opts.items || []).slice();
  var prefix = opts.prefix || "";

  var pop = document.createElement("div");
  pop.className = "todo-popover";
  pop.style.minWidth = "16rem";

  var titleEl = document.createElement("div");
  titleEl.style.cssText =
    "font-size:0.75rem;font-weight:600;color:var(--bs-secondary-color);margin-bottom:0.5rem;";
  titleEl.textContent = opts.title || "";
  pop.appendChild(titleEl);

  var pillsEl = document.createElement("div");
  pillsEl.style.cssText =
    "display:flex;flex-wrap:wrap;gap:0.25rem;margin-bottom:0.5rem;min-height:1.5rem;";
  pop.appendChild(pillsEl);

  function renderPills() {
    pillsEl.innerHTML = "";
    itemSet.forEach(function (item) {
      var pill = document.createElement("span");
      pill.style.cssText =
        "display:inline-flex;align-items:center;gap:0.25rem;background:var(--bs-secondary-bg);border-radius:9999px;padding:0.1rem 0.45rem;font-size:0.78rem;";
      pill.textContent = prefix + item;
      var rm = document.createElement("button");
      rm.type = "button";
      rm.style.cssText =
        "border:none;background:none;padding:0;cursor:pointer;font-size:0.7rem;color:var(--bs-secondary-color);line-height:1;";
      rm.textContent = "×";
      rm.addEventListener(
        "click",
        (function (v) {
          return function (e) {
            e.stopPropagation();
            itemSet = itemSet.filter(function (x) {
              return x !== v;
            });
            renderPills();
          };
        })(item),
      );
      pill.appendChild(rm);
      pillsEl.appendChild(pill);
    });
  }
  renderPills();

  var input = document.createElement("input");
  input.type = "text";
  input.className = "form-control form-control-sm";
  input.placeholder = opts.placeholder || "Add…";
  pop.appendChild(input);

  var suggestEl = document.createElement("div");
  suggestEl.style.cssText =
    "display:flex;flex-wrap:wrap;gap:0.2rem;margin-top:0.3rem;";
  pop.appendChild(suggestEl);

  function renderSuggestions(all) {
    suggestEl.innerHTML = "";
    var pfx = prefix;
    var q = input.value
      .trim()
      .toLowerCase()
      .replace(
        new RegExp("^" + pfx.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
        "",
      );
    var available = all
      .filter(function (v) {
        return itemSet.indexOf(v) === -1 && (!q || v.toLowerCase().includes(q));
      })
      .slice(0, 8);
    available.forEach(function (v) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.style.cssText =
        "border:1px solid var(--bs-border-color);background:#fff;border-radius:9999px;padding:0.1rem 0.5rem;font-size:0.75rem;cursor:pointer;";
      chip.textContent = pfx + v;
      chip.addEventListener(
        "click",
        (function (val) {
          return function (e) {
            e.stopPropagation();
            if (itemSet.indexOf(val) === -1) itemSet.push(val);
            input.value = "";
            renderPills();
            renderSuggestions(all);
          };
        })(v),
      );
      suggestEl.appendChild(chip);
    });
  }

  if (opts.suggestUrl) {
    fetch(opts.suggestUrl)
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        var all = opts.suggestTransform
          ? opts.suggestTransform(data)
          : Array.isArray(data)
            ? data
            : [];
        renderSuggestions(all);
        input.addEventListener("input", function () {
          renderSuggestions(all);
        });
        input.addEventListener("keydown", function (e) {
          if (e.key === "Escape") {
            e.preventDefault();
            tryClose();
            return;
          }
          if (e.key === "Enter") {
            e.preventDefault();
            var val = input.value
              .trim()
              .replace(
                new RegExp("^" + prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
                "",
              );
            if (val && itemSet.indexOf(val) === -1) itemSet.push(val);
            input.value = "";
            renderPills();
            renderSuggestions(all);
          }
        });
      })
      .catch(function () {});
  } else {
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        e.preventDefault();
        tryClose();
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        var val = input.value
          .trim()
          .replace(
            new RegExp("^" + prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
            "",
          );
        if (val && itemSet.indexOf(val) === -1) itemSet.push(val);
        input.value = "";
        renderPills();
      }
    });
  }

  var warnEl = document.createElement("div");
  warnEl.style.cssText =
    "display:none;color:var(--bs-danger);font-size:0.75rem;margin-top:0.3rem;";
  pop.appendChild(warnEl);

  function tryClose(after) {
    var pending = input.value.trim();
    if (pending) {
      warnEl.textContent =
        'Press Enter to add "' + pending + '" or clear the input first.';
      warnEl.style.display = "block";
      input.focus();
      return false;
    }
    closePopovers();
    if (after) after();
    return true;
  }
  input.addEventListener("input", function () {
    if (warnEl.style.display !== "none") warnEl.style.display = "none";
  });

  var footer = document.createElement("div");
  footer.className = "todo-popover-actions";
  footer.style.marginTop = "0.5rem";
  var setBtn = document.createElement("button");
  setBtn.type = "button";
  setBtn.className = "btn btn-sm btn-dark";
  setBtn.textContent = "Set";
  var cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "btn btn-sm btn-link text-muted";
  cancelBtn.textContent = "Cancel";
  footer.appendChild(setBtn);
  footer.appendChild(cancelBtn);
  pop.appendChild(footer);

  setBtn.addEventListener("click", function () {
    tryClose(function () {
      if (opts.onCommit) opts.onCommit(itemSet);
    });
  });
  cancelBtn.addEventListener("click", function () {
    tryClose();
  });

  anchorPopover(pop, opts.anchorEl);
  setTimeout(function () {
    input.focus();
  }, 0);
}

// --- Tags picker (wrapper around _openItemsPicker) ---------------------------

function openTagsPicker(itemEl, anchorEl) {
  _openItemsPicker({
    anchorEl: anchorEl || itemEl,
    title: "Tags",
    items: _readTagsFromDetailsPanel(),
    placeholder: "Add tag…",
    prefix: "#",
    suggestUrl: "/todos/tags.json",
    suggestTransform: function (data) {
      return data.map
        ? data.map(function (t) {
            return typeof t === "string" ? t : t.tag || t.name || String(t);
          })
        : [];
    },
    onCommit: _renderTagsIntoDetailsPanel,
  });
}

function _readTagsFromDetailsPanel() {
  var panel = document.getElementById("details-panel");
  if (!panel) return [];
  return Array.from(
    panel.querySelectorAll('input[type="hidden"][name^="tags."]'),
  ).map(function (i) {
    return i.value;
  });
}

// --- Details panel field rendering ------------------------------------------
// Helpers below mutate the details panel so its hidden inputs reflect the
// chosen values, then trigger the form submit so htmx/form-json PUT the
// payload to todo_update.

function _detailsPanel() {
  return document.getElementById("details-panel");
}
function _detailsForm() {
  var panel = _detailsPanel();
  return panel ? panel.querySelector("form") : null;
}
function _submitDetailsForm() {
  var form = _detailsForm();
  if (form) form.requestSubmit();
}
function _setClearMarker(fieldName, cleared) {
  // Maintains a `clear_fields.N` hidden input set listing fields the server
  // should explicitly null out (form-json drops absent fields, so missing
  // != cleared without this). form-json's indexed dot notation produces
  // a JSON array on submit.
  var form = _detailsForm();
  if (!form) return;
  var existing = Array.from(
    form.querySelectorAll('input[name^="clear_fields."]'),
  );
  var current = existing.map(function (i) {
    return i.value;
  });
  var pos = current.indexOf(fieldName);
  if (cleared && pos === -1) current.push(fieldName);
  if (!cleared && pos !== -1) current.splice(pos, 1);
  existing.forEach(function (i) {
    i.remove();
  });
  current.forEach(function (name, idx) {
    var input = document.createElement("input");
    input.type = "hidden";
    input.name = "clear_fields." + idx;
    input.value = name;
    form.appendChild(input);
  });
}
function _findOrCreateDetailsRow(className, label) {
  var panel = _detailsPanel();
  if (!panel) return null;
  var row = panel.querySelector("." + className);
  if (!row) {
    row = document.createElement("div");
    row.className = "details-field-row " + className;
    var labelEl = document.createElement("span");
    labelEl.className = "details-field-label";
    labelEl.textContent = label;
    var valueEl = document.createElement("span");
    valueEl.className = "details-field-value";
    row.appendChild(labelEl);
    row.appendChild(valueEl);
    var addRow = panel.querySelector(".details-add-fields-row");
    if (addRow) addRow.parentNode.insertBefore(row, addRow);
    else panel.appendChild(row);
  }
  return row;
}

function _renderTagsIntoDetailsPanel(items) {
  var panel = _detailsPanel();
  if (!panel) return;
  _setClearMarker("tags", !items.length);
  var row = panel.querySelector(".details-field--tags");
  if (!items.length) {
    if (row) row.remove();
  } else {
    row = row || _findOrCreateDetailsRow("details-field--tags", "Tags");
    var value = row.querySelector(".details-field-value");
    value.innerHTML = "";
    items.forEach(function (tag, idx) {
      var pill = document.createElement("span");
      pill.className = "details-tag-pill";
      pill.textContent = "#" + tag;
      value.appendChild(pill);
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "tags." + idx;
      hidden.value = tag;
      value.appendChild(hidden);
    });
  }
  _submitDetailsForm();
}

function _renderAssigneesIntoDetailsPanel(items) {
  var panel = _detailsPanel();
  if (!panel) return;
  _setClearMarker("assignees", !items.length);
  var row = panel.querySelector(".details-field--assignees");
  if (!items.length) {
    if (row) row.remove();
  } else {
    row =
      row || _findOrCreateDetailsRow("details-field--assignees", "Assigned");
    var value = row.querySelector(".details-field-value");
    value.innerHTML = "";
    items.forEach(function (name, idx) {
      var pill = document.createElement("span");
      pill.className = "details-assignee-pill";
      pill.textContent = "@" + name;
      value.appendChild(pill);
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "assignees." + idx;
      hidden.value = name;
      value.appendChild(hidden);
    });
  }
  _submitDetailsForm();
}

function _renderDueIntoDetailsPanel(iso) {
  var panel = _detailsPanel();
  if (!panel) return;
  _setClearMarker("due_date", !iso);
  var row = panel.querySelector(".details-field--due");
  if (!iso) {
    if (row) row.remove();
  } else {
    row = row || _findOrCreateDetailsRow("details-field--due", "Due");
    var value = row.querySelector(".details-field-value");
    value.textContent = iso;
    Array.from(row.querySelectorAll('input[name="due_date"]')).forEach(
      function (i) {
        i.remove();
      },
    );
    var hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = "due_date";
    hidden.value = iso;
    row.appendChild(hidden);
  }
  _submitDetailsForm();
}

function _renderNoteIntoDetailsPanel(text) {
  var panel = _detailsPanel();
  if (!panel) return;
  _setClearMarker("note", !text);
  var row = panel.querySelector(".details-field--note");
  if (!text) {
    if (row) row.remove();
  } else {
    row = row || _findOrCreateDetailsRow("details-field--note", "Note");
    var value = row.querySelector(".details-field-value");
    value.textContent = text;
    Array.from(row.querySelectorAll('input[name="note"]')).forEach(
      function (i) {
        i.remove();
      },
    );
    var hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = "note";
    hidden.value = text;
    row.appendChild(hidden);
  }
  _submitDetailsForm();
}

function _renderRecurrenceIntoDetailsPanel(spec, label) {
  // spec: null to clear, else {kind, interval_value, interval_unit, weekday?, month_day?}
  var panel = _detailsPanel();
  if (!panel) return;
  _setClearMarker("recurrence", !spec);
  var row = panel.querySelector(".details-field--rec");
  if (!spec) {
    if (row) row.remove();
  } else {
    row = row || _findOrCreateDetailsRow("details-field--rec", "Repeat");
    var value = row.querySelector(".details-field-value");
    value.textContent = label || "";
    Array.from(row.querySelectorAll('input[name^="recurrence."]')).forEach(
      function (i) {
        i.remove();
      },
    );
    var fields = [
      ["recurrence.kind", spec.kind],
      ["recurrence.interval_value", spec.interval_value],
      ["recurrence.interval_unit", spec.interval_unit],
    ];
    if (spec.weekday !== null && spec.weekday !== undefined) {
      fields.push(["recurrence.weekday", spec.weekday]);
    }
    if (spec.month_day !== null && spec.month_day !== undefined) {
      fields.push(["recurrence.month_day", spec.month_day]);
    }
    fields.forEach(function (f) {
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = f[0];
      hidden.value = String(f[1]);
      row.appendChild(hidden);
    });
  }
  _submitDetailsForm();
}

function _renderLinksIntoDetailsPanel(links) {
  // links: [{label?, url}]
  var panel = _detailsPanel();
  if (!panel) return;
  _setClearMarker("links", !links.length);
  var row = panel.querySelector(".details-field--links");
  if (!links.length) {
    if (row) row.remove();
  } else {
    row = row || _findOrCreateDetailsRow("details-field--links", "Links");
    var value = row.querySelector(".details-field-value");
    value.innerHTML = "";
    links.forEach(function (link, idx) {
      var item = document.createElement("span");
      item.className = "details-link-item me-1 text-nowrap";
      item.dataset.linkIdx = String(idx);

      var a = document.createElement("a");
      a.href = link.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.className = "small";
      a.textContent = link.label || link.url;
      item.appendChild(a);

      var editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "btn btn-link btn-sm p-0 details-link-edit";
      editBtn.title = "Edit";
      editBtn.innerHTML =
        '<i class="bi bi-pencil" style="font-size:0.6rem;vertical-align:middle"></i>';
      item.appendChild(editBtn);

      var rmBtn = document.createElement("button");
      rmBtn.type = "button";
      rmBtn.className =
        "btn btn-link btn-sm p-0 text-danger details-link-remove";
      rmBtn.title = "Remove";
      rmBtn.innerHTML =
        '<i class="bi bi-x" style="font-size:0.75rem;vertical-align:middle"></i>';
      item.appendChild(rmBtn);

      var urlInput = document.createElement("input");
      urlInput.type = "hidden";
      urlInput.name = "links." + idx + ".url";
      urlInput.value = link.url;
      item.appendChild(urlInput);

      var labelInput = document.createElement("input");
      labelInput.type = "hidden";
      labelInput.name = "links." + idx + ".label";
      labelInput.value = link.label || "";
      item.appendChild(labelInput);

      value.appendChild(item);
    });
  }
  _submitDetailsForm();
}

function _readAssigneesFromDetailsPanel() {
  var panel = _detailsPanel();
  if (!panel) return [];
  return Array.from(
    panel.querySelectorAll('input[type="hidden"][name^="assignees."]'),
  ).map(function (i) {
    return i.value;
  });
}

function _readNoteFromDetailsPanel() {
  var panel = _detailsPanel();
  if (!panel) return "";
  var input = panel.querySelector('input[type="hidden"][name="note"]');
  return input ? input.value : "";
}

function _readDueFromDetailsPanel() {
  var panel = _detailsPanel();
  if (!panel) return "";
  var input = panel.querySelector('input[type="hidden"][name="due_date"]');
  return input ? input.value : "";
}

function _readRecurrenceLabelFromDetailsPanel() {
  var panel = _detailsPanel();
  if (!panel) return "";
  var row = panel.querySelector(".details-field--rec");
  if (!row) return "";
  var v = row.querySelector(".details-field-value");
  return v ? v.textContent.trim() : "";
}

function openNotePickerForDetails(anchorEl) {
  openNotePicker({
    anchorEl: anchorEl,
    initialNote: _readNoteFromDetailsPanel(),
    title: "Note",
    onCommit: _renderNoteIntoDetailsPanel,
  });
}

function openLinkPickerForDetails(anchorEl) {
  var existing = _readLinksFromDetailsPanel();
  openLinkPicker({
    anchorEl: anchorEl,
    onCommit: function (raw) {
      var parsed = _parseLinkLiteral(raw);
      if (parsed) _renderLinksIntoDetailsPanel(existing.concat([parsed]));
    },
  });
}

function _readLinksFromDetailsPanel() {
  var panel = _detailsPanel();
  if (!panel) return [];
  var byIdx = {};
  panel
    .querySelectorAll('input[type="hidden"][name^="links."]')
    .forEach(function (input) {
      var m = input.name.match(/^links\.(\d+)\.(label|url)$/);
      if (!m) return;
      var idx = parseInt(m[1], 10);
      if (!byIdx[idx]) byIdx[idx] = { label: "", url: "" };
      byIdx[idx][m[2]] = input.value;
    });
  return Object.keys(byIdx)
    .map(Number)
    .sort(function (a, b) {
      return a - b;
    })
    .map(function (idx) {
      return byIdx[idx];
    });
}

// --- Assignees picker (wrapper around _openItemsPicker) ----------------------

function openAssigneesPicker(itemEl, anchorEl) {
  _openItemsPicker({
    anchorEl: anchorEl || itemEl,
    title: "Assign",
    items: _readAssigneesFromDetailsPanel(),
    placeholder: "Add person…",
    prefix: "@",
    suggestUrl: "/todos/principals.json",
    suggestTransform: function (data) {
      return Array.isArray(data)
        ? data.map(function (p) {
            return p.name || String(p);
          })
        : [];
    },
    onCommit: _renderAssigneesIntoDetailsPanel,
  });
}

// --- Repetition history panel ---
function openHistoryPanel(itemEl) {
  var url = itemEl.dataset.historyUrl;
  if (!url) return;
  closePopovers();
  closeHistoryPanel();
  fetch(url, { headers: { Accept: "text/html" } })
    .then(function (r) {
      return r.text();
    })
    .then(function (html) {
      var wrap = document.createElement("div");
      wrap.id = "todo-history-wrap";
      wrap.innerHTML = html;
      document.body.appendChild(wrap);
    });
}
function closeHistoryPanel() {
  var w = document.getElementById("todo-history-wrap");
  if (w) w.remove();
}
document.addEventListener("click", function (e) {
  if (e.target.closest(".todo-history-close")) {
    closeHistoryPanel();
    return;
  }
  var rec = e.target.closest(".todo-recurrence");
  if (rec) {
    var item = rec.closest(".todo-item");
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
    _kbdRow("d", "Set / change due date"),
    _kbdRow("f", "Set / change repetition rule"),
    _kbdRow("s", "Edit tags"),
    _kbdRow("p", "Postpone selected by 1 day"),
    _kbdRow("Shift+P", "Postpone\u2026 (palette + calendar)"),
    _kbdRow("r", "Open protocol palette \u2014 start a run"),
    _kbdRow("[", "Collapse all groups"),
    _kbdRow("]", "Expand all groups"),
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
    _kbdRow("swipe \u2192", "Same as <kbd>c</kbd>"),
    _kbdRow("swipe \u2190", "Same as <kbd>t</kbd>"),
    "</tbody></table>",

    _kbdSection("Adding a todo"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("#tag", "Attach a tag (single word)"),
    _kbdRow("^", "Open the date picker"),
    _kbdRow("*", "Open the repetition picker"),
    "</tbody></table>",

    _kbdSection("Done list"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("click", "Select / deselect item"),
    _kbdRow("r", "Restore selected items"),
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

// Details pane: field row & "+" chip clicks are wired via hyperscript in
// _todo_details_panel.pt.

// Details pane: link edit/remove/add buttons
function _parseLinkLiteral(raw) {
  if (!raw) return null;
  var m = String(raw).match(
    /^\[([^\]]*)\]\(([a-zA-Z][a-zA-Z0-9+\-.]*:\/\/[^)]+)\)$/,
  );
  if (!m) return null;
  return { label: m[1] || null, url: m[2] };
}
function _formatLinkLiteral(link) {
  return "[" + (link.label || "") + "](" + link.url + ")";
}

document.addEventListener("click", function (e) {
  var editBtn = e.target.closest(".details-link-edit");
  if (editBtn) {
    e.preventDefault();
    e.stopPropagation();
    var item = editBtn.closest(".details-link-item");
    var idx = item ? parseInt(item.dataset.linkIdx, 10) : -1;
    var links = _readLinksFromDetailsPanel();
    if (idx < 0 || !links[idx]) return;
    var row = editBtn.closest(".details-field--links");
    openLinkPicker({
      anchorEl: row || editBtn,
      initialLink: _formatLinkLiteral(links[idx]),
      onCommit: function (raw) {
        var parsed = _parseLinkLiteral(raw);
        if (!parsed) return;
        var updated = links.slice();
        updated[idx] = parsed;
        _renderLinksIntoDetailsPanel(updated);
      },
    });
    return;
  }

  var removeBtn = e.target.closest(".details-link-remove");
  if (removeBtn) {
    e.preventDefault();
    e.stopPropagation();
    var item = removeBtn.closest(".details-link-item");
    var idx = item ? parseInt(item.dataset.linkIdx, 10) : -1;
    var links = _readLinksFromDetailsPanel();
    if (idx < 0) return;
    _renderLinksIntoDetailsPanel(
      links.filter(function (_, i) {
        return i !== idx;
      }),
    );
    return;
  }

  var addBtn = e.target.closest(".details-add-link");
  if (addBtn) {
    e.preventDefault();
    e.stopPropagation();
    var links = _readLinksFromDetailsPanel();
    var row = addBtn.closest(".details-field--links");
    openLinkPicker({
      anchorEl: row || addBtn,
      onCommit: function (raw) {
        var parsed = _parseLinkLiteral(raw);
        if (parsed) _renderLinksIntoDetailsPanel(links.concat([parsed]));
      },
    });
    return;
  }
});

// Details pane: "Add field" chip buttons are wired via hyperscript in
// _todo_details_panel.pt.

// --- Protocol run page interactions ----------------------------------------
//
// Run-item actions (done / send-to-todo / edit) are dispatched via delegation
// on .protocol-run-action buttons inside #protocol-run. Each .protocol-run-item
// carries data-done-url / data-send-url / data-edit-url to keep the JS
// parameter-free.

(function _wireRunActions() {
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".protocol-run-action");
    if (!btn) return;
    var item = btn.closest(".protocol-run-item");
    if (!item) return;
    var action = btn.dataset.action;
    if (action === "edit") return runItemEditInline(item);
    var url = action === "done" ? item.dataset.doneUrl : item.dataset.sendUrl;
    var run = document.getElementById("protocol-run");
    if (!url || !run) return;
    e.preventDefault();
    htmx.ajax("POST", url, { target: run, swap: "innerHTML transition:true" });
  });
})();

function runItemEditInline(itemEl) {
  var textSpan = itemEl.querySelector(".flex-grow-1 > span");
  if (!textSpan) return;
  var existing = textSpan.textContent.trim();
  var input = document.createElement("input");
  input.type = "text";
  input.value = existing;
  input.className = "form-control form-control-sm";
  input.style.maxWidth = "20rem";
  textSpan.replaceWith(input);
  input.focus();
  input.select();
  function commit() {
    var run = document.getElementById("protocol-run");
    var url = itemEl.dataset.editUrl;
    if (!url || !run) return;
    htmx.ajax("POST", url, {
      target: run,
      swap: "innerHTML",
      values: { text: input.value },
    });
  }
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      input.replaceWith(textSpan);
    }
  });
  input.addEventListener("blur", commit);
}

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

// --- Swipe for run items ---
var _runSwipeState = new WeakMap();
document.addEventListener(
  "touchstart",
  function (e) {
    var item = e.target.closest(".protocol-run-item");
    if (!item) return;
    var inner = item.querySelector(".todo-content");
    if (!inner) return;
    inner.style.transition = "none";
    _runSwipeState.set(item, { startX: e.touches[0].clientX, dx: 0 });
  },
  { passive: true },
);
document.addEventListener(
  "touchmove",
  function (e) {
    var item = e.target.closest(".protocol-run-item");
    if (!item) return;
    var s = _runSwipeState.get(item);
    if (!s) return;
    var inner = item.querySelector(".todo-content");
    if (!inner) return;
    s.dx = e.touches[0].clientX - s.startX;
    inner.style.transform =
      "translateX(" + Math.max(-150, Math.min(150, s.dx)) + "px)";
    item.dataset.swipeDir = s.dx > 0 ? "right" : s.dx < 0 ? "left" : "";
  },
  { passive: true },
);
document.addEventListener("touchend", function (e) {
  var item = e.target.closest(".protocol-run-item");
  if (!item) return;
  var s = _runSwipeState.get(item);
  if (!s) return;
  _runSwipeState.delete(item);
  var inner = item.querySelector(".todo-content");
  if (!inner) return;
  inner.style.transition = "transform 0.2s ease";
  var dx = s.dx;
  if (dx >= 80) {
    inner.style.transform = "translateX(100vw)";
    var btn = item.querySelector('.protocol-run-action[data-action="done"]');
    if (btn) btn.click();
  } else if (dx <= -80) {
    inner.style.transform = "translateX(-100vw)";
    var sendBtn = item.querySelector(
      '.protocol-run-action[data-action="send"]',
    );
    if (sendBtn) sendBtn.click();
  } else {
    inner.style.transform = "translateX(0)";
    delete item.dataset.swipeDir;
  }
});

// --- Protocol palette (r key on /todos) ---
var _palette = null;

function openProtocolPalette() {
  if (_palette) return;
  _palette = document.createElement("div");
  _palette.className = "protocol-palette";
  var input = document.createElement("input");
  input.type = "text";
  input.className = "protocol-palette-input";
  input.placeholder = "Start a protocol \u2014 type to filter";
  var list = document.createElement("ul");
  list.className = "protocol-palette-list";
  _palette.appendChild(input);
  _palette.appendChild(list);
  document.body.appendChild(_palette);
  input.focus();

  var protocols = [];
  var selected = 0;

  function render(filter) {
    list.innerHTML = "";
    var q = filter.trim().toLowerCase();
    var matches = q
      ? protocols.filter(function (p) {
          return p.title.toLowerCase().includes(q);
        })
      : protocols;
    if (!matches.length) {
      var empty = document.createElement("li");
      empty.className = "protocol-palette-empty";
      empty.textContent = q ? "No matches." : "No protocols defined yet.";
      list.appendChild(empty);
      return;
    }
    selected = Math.min(selected, matches.length - 1);
    matches.forEach(function (p, i) {
      var li = document.createElement("li");
      li.className =
        "protocol-palette-item" + (i === selected ? " is-selected" : "");
      li.textContent = p.title;
      li.dataset.id = p.id;
      li.addEventListener("click", function () {
        startRun(p.id);
      });
      list.appendChild(li);
    });
  }

  function startRun(id) {
    closeProtocolPalette();
    var form = document.createElement("form");
    form.method = "post";
    form.action = "/protocols/" + id + "/start";
    document.body.appendChild(form);
    form.submit();
  }

  fetch("/protocols/palette.json")
    .then(function (r) {
      return r.json();
    })
    .then(function (data) {
      protocols = data;
      render("");
    });

  input.addEventListener("input", function () {
    selected = 0;
    render(input.value);
  });
  input.addEventListener("keydown", function (e) {
    var items = list.querySelectorAll(".protocol-palette-item");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      selected = Math.min(items.length - 1, selected + 1);
      render(input.value);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      selected = Math.max(0, selected - 1);
      render(input.value);
    } else if (e.key === "Enter") {
      e.preventDefault();
      var current = items[selected];
      if (current) startRun(current.dataset.id);
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeProtocolPalette();
    }
  });
}

function closeProtocolPalette() {
  if (_palette) {
    _palette.remove();
    _palette = null;
  }
}

document.addEventListener("mousedown", function (e) {
  if (!_palette) return;
  if (e.target.closest(".protocol-palette")) return;
  closeProtocolPalette();
});

document.addEventListener("keydown", function (e) {
  if (e.key !== "r") return;
  if (
    e.target.tagName === "INPUT" ||
    e.target.tagName === "TEXTAREA" ||
    e.target.contentEditable === "true"
  )
    return;
  // Only on the todo list page (avoid interfering with the done page's r=restore)
  if (!document.getElementById("todo-list")) return;
  if (document.getElementById("done-list")) return; // /todos/done page
  e.preventDefault();
  openProtocolPalette();
});

// --- Protocol item editor — uses CompositeInput (tags + note only) -----------

function initProtocolItemInputs() {
  document.querySelectorAll(".proto-item-form").forEach(function (form) {
    var container = form.querySelector(".ci-container");
    if (!container) return;
    CompositeInput(container, {
      textOuter: container.querySelector(".ci-text"),
      hiddenInput: form.querySelector(".ci-hidden-input"),
      saveBtn: form.querySelector(".ci-save-btn"),
      form: form,
      tags: true,
      note: true,
      recurrence: false,
      dueDate: false,
      assignees: true,
      principalsUrl: "/todos/principals.json",
    });
  });
}

function initProtocolNewItemInput() {
  var container = document.querySelector(".proto-new-item-ci");
  if (!container) return;
  var form = document.getElementById("proto-new-item-form");
  var protocolId = form ? form.dataset.protocolId : null;
  var sessionKey = protocolId ? "proto-new-item-tags-" + protocolId : null;
  var focusKey = protocolId ? "proto-new-item-focus-" + protocolId : null;

  CompositeInput(container, {
    textOuter: container.querySelector(".ci-text"),
    hiddenInput: form ? form.querySelector(".ci-hidden-input") : null,
    form: form,
    tags: true,
    note: true,
    recurrence: false,
    dueDate: false,
    assignees: true,
    principalsUrl: "/todos/principals.json",
    sessionKey: sessionKey,
    placeholder: "New item…",
  });

  var scrollKey = protocolId ? "proto-scroll-" + protocolId : null;

  if (scrollKey) {
    var savedScroll = sessionStorage.getItem(scrollKey);
    if (savedScroll) {
      sessionStorage.removeItem(scrollKey);
      requestAnimationFrame(function () {
        window.scrollTo({
          top: parseInt(savedScroll, 10),
          behavior: "instant",
        });
      });
    }
  }

  if (focusKey && sessionStorage.getItem(focusKey)) {
    sessionStorage.removeItem(focusKey);
    var seg = container.querySelector(".todo-text-seg");
    if (seg) {
      seg.focus();
    }
  }

  if (form) {
    form.addEventListener("submit", function () {
      if (focusKey) sessionStorage.setItem(focusKey, "1");
      if (scrollKey) sessionStorage.setItem(scrollKey, String(window.scrollY));
    });
  }
}

function deleteProtocolItem(btn) {
  var li = btn.closest("li");
  if (!li) return;
  var url = btn.dataset.deleteUrl;
  var saved = li.outerHTML;
  var placeholder = document.createElement("li");
  placeholder.className = "card mb-1";
  placeholder.innerHTML =
    '<div class="card-body py-1 px-3 d-flex align-items-center gap-2">' +
    '<span class="text-muted small">Item deleted.</span>' +
    '<button type="button" class="btn btn-link btn-sm p-0">Undo</button>' +
    "</div>";
  placeholder._deleteTimer = setTimeout(function () {
    fetch(url, { method: "POST" }).then(function (r) {
      if (!r.ok) {
        placeholder.insertAdjacentHTML("beforebegin", saved);
        placeholder.remove();
      } else {
        placeholder.remove();
      }
    });
  }, 5000);
  placeholder.querySelector("button").addEventListener("click", function () {
    clearTimeout(placeholder._deleteTimer);
    placeholder.insertAdjacentHTML("beforebegin", saved);
    placeholder.remove();
    initProtocolItemInputs();
  });
  li.replaceWith(placeholder);
}

function initProtocolTitleInput() {
  var container = document.getElementById("proto-title-ci");
  if (!container) return;
  var form = document.getElementById("proto-title-form");
  CompositeInput(container, {
    textOuter: container.querySelector(".ci-text"),
    hiddenInput: form ? form.querySelector(".ci-hidden-input") : null,
    quickPickEl: form ? form.querySelector(".ci-quick-pick") : null,
    form: form,
    tags: true,
    note: true,
    recurrence: true,
    dueDate: false,
    assignees: true,
    principalsUrl: "/todos/principals.json",
    placeholder: "Protocol title…",
  });
}

htmx.onLoad(function (content) {
  ensureHelpOverlay();
  initSortables(content);
  initTodoSwipe(content);
  initTagInput();
  initProtocolItemInputs();
  initProtocolTitleInput();
  initProtocolNewItemInput();
  if (document.getElementById("protocol-run")) _runHighlight();
});
ensureHelpOverlay();
initSortables(document);
initTodoSwipe(document);
initTagInput();
initProtocolItemInputs();
initProtocolTitleInput();
initProtocolNewItemInput();
if (document.getElementById("protocol-run")) _runHighlight();
