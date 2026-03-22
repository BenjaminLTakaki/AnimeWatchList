/* ── Modal ──────────────────────────────────────────────────────────── */
function openModal(id) {
  document.getElementById(id).classList.add('open');
}
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

// Close modal on overlay click
document.addEventListener('click', function(e) {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
  }
});

// Close modal on Escape
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(function(m) {
      m.classList.remove('open');
    });
  }
});

/* ── Add-to-list modal ──────────────────────────────────────────────── */
function openAddModal(malId, title, imageUrl, episodes) {
  var modal = document.getElementById('add-modal');
  if (!modal) return;

  modal.querySelector('#modal-title').textContent = title;
  modal.querySelector('#modal-mal-id').value = malId;

  var thumb = modal.querySelector('#modal-thumb');
  if (imageUrl) {
    thumb.src = imageUrl;
    thumb.style.display = 'block';
  } else {
    thumb.style.display = 'none';
  }

  var epsSection = modal.querySelector('#modal-eps-section');
  if (episodes && parseInt(episodes) > 0) {
    var slider = modal.querySelector('#modal-eps');
    slider.max = episodes;
    slider.value = 0;
    modal.querySelector('#modal-eps-label').textContent = '0/' + episodes;
    epsSection.style.display = 'block';
  } else {
    epsSection.style.display = 'none';
  }

  // Reset status + score
  document.querySelectorAll('.status-btn').forEach(function(b) { b.classList.remove('active'); });
  var ptw = modal.querySelector('[data-status="plan_to_watch"]');
  if (ptw) ptw.classList.add('active');
  modal.querySelector('#modal-status').value = 'plan_to_watch';

  document.querySelectorAll('.score-btn').forEach(function(b) { b.classList.remove('active'); });
  modal.querySelector('#modal-score').value = '';

  openModal('add-modal');
}

// Status buttons
document.addEventListener('click', function(e) {
  var btn = e.target.closest('.status-btn');
  if (!btn) return;
  var grid = btn.closest('.status-grid');
  grid.querySelectorAll('.status-btn').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  var hiddenInput = document.querySelector('#modal-status');
  if (hiddenInput) hiddenInput.value = btn.dataset.status;
});

// Score buttons
document.addEventListener('click', function(e) {
  var btn = e.target.closest('.score-btn');
  if (!btn) return;
  var grid = btn.closest('.score-grid');
  var current = document.querySelector('#modal-score').value;
  var val = btn.dataset.score;
  if (current === val) {
    grid.querySelectorAll('.score-btn').forEach(function(b) { b.classList.remove('active'); });
    document.querySelector('#modal-score').value = '';
  } else {
    grid.querySelectorAll('.score-btn').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
    document.querySelector('#modal-score').value = val;
  }
});

// Episode slider
var epsSlider = document.querySelector('#modal-eps');
if (epsSlider) {
  epsSlider.addEventListener('input', function() {
    document.querySelector('#modal-eps-label').textContent = this.value + '/' + this.max;
  });
}

/* ── Live search ────────────────────────────────────────────────────── */
var searchTimeout;
var searchInput = document.querySelector('#live-search');
if (searchInput) {
  searchInput.addEventListener('input', function() {
    clearTimeout(searchTimeout);
    var q = this.value.trim();
    if (!q) return;
    var spinner = document.querySelector('.search-spinner');
    if (spinner) spinner.classList.add('active');
    searchTimeout = setTimeout(function() {
      window.location.href = window.location.pathname + '?q=' + encodeURIComponent(q);
    }, 600);
  });
}

/* ── Inline edit (list page) ─────────────────────────────────────────── */
function openEdit(malId, status, score) {
  var row = document.querySelector('[data-mal-id="' + malId + '"]');
  if (!row) return;
  row.querySelector('.view-mode').style.display = 'none';
  row.querySelector('.edit-mode').style.display = 'flex';
  var sel = row.querySelector('.edit-status');
  if (sel) sel.value = status;
  var sc = row.querySelector('.edit-score');
  if (sc) sc.value = score || '';
}

function cancelEdit(malId) {
  var row = document.querySelector('[data-mal-id="' + malId + '"]');
  if (!row) return;
  row.querySelector('.view-mode').style.display = '';
  row.querySelector('.edit-mode').style.display = 'none';
}

/* ── Auto-dismiss flash ──────────────────────────────────────────────── */
setTimeout(function() {
  document.querySelectorAll('.flash').forEach(function(f) {
    f.style.transition = 'opacity .4s';
    f.style.opacity = '0';
    setTimeout(function() { f.remove(); }, 400);
  });
}, 3500);
