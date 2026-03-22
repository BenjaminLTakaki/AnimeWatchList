/* ── Hamburger Menu ──────────────────────────────────────────────────── */
(function() {
  var hamburger = document.querySelector('.nav-hamburger');
  var navLinks  = document.querySelector('.nav-links');
  if (!hamburger || !navLinks) return;

  hamburger.addEventListener('click', function() {
    hamburger.classList.toggle('open');
    navLinks.classList.toggle('open');
  });

  // Close on nav link click (mobile)
  navLinks.querySelectorAll('.nav-link').forEach(function(link) {
    link.addEventListener('click', function() {
      hamburger.classList.remove('open');
      navLinks.classList.remove('open');
    });
  });
})();

/* ── Modal ──────────────────────────────────────────────────────────── */
function openModal(id) {
  document.getElementById(id).classList.add('open');
}
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

document.addEventListener('click', function(e) {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
  }
});

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
  if (thumb) {
    if (imageUrl) { thumb.src = imageUrl; thumb.style.display = 'block'; }
    else { thumb.style.display = 'none'; }
  }

  var epsSection = modal.querySelector('#modal-eps-section');
  if (epsSection) {
    if (episodes && parseInt(episodes) > 0) {
      var slider = modal.querySelector('#modal-eps');
      slider.max = episodes;
      slider.value = 0;
      modal.querySelector('#modal-eps-label').textContent = '0/' + episodes;
      epsSection.style.display = 'block';
    } else {
      epsSection.style.display = 'none';
    }
  }

  // Reset
  modal.querySelectorAll('.status-btn').forEach(function(b) { b.classList.remove('active'); });
  var ptw = modal.querySelector('[data-status="plan_to_watch"]');
  if (ptw) ptw.classList.add('active');
  var statusInput = modal.querySelector('#modal-status');
  if (statusInput) statusInput.value = 'plan_to_watch';

  modal.querySelectorAll('.score-btn').forEach(function(b) { b.classList.remove('active'); });
  var scoreInput = modal.querySelector('#modal-score');
  if (scoreInput) scoreInput.value = '';

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
  var scoreInput = document.querySelector('#modal-score');
  var current = scoreInput ? scoreInput.value : '';
  var val = btn.dataset.score;
  if (current === val) {
    grid.querySelectorAll('.score-btn').forEach(function(b) { b.classList.remove('active'); });
    if (scoreInput) scoreInput.value = '';
  } else {
    grid.querySelectorAll('.score-btn').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
    if (scoreInput) scoreInput.value = val;
  }
});

// Episode slider
var epsSlider = document.querySelector('#modal-eps');
if (epsSlider) {
  epsSlider.addEventListener('input', function() {
    document.querySelector('#modal-eps-label').textContent = this.value + '/' + this.max;
  });
}

/* ── Star Rating ───────────────────────────────────────────────────── */
function createStarDisplay(rating) {
  var html = '<span class="star-display">';
  for (var i = 1; i <= 5; i++) {
    html += '<span class="' + (i <= rating ? '' : 'empty') + '">' + (i <= rating ? '\u2605' : '\u2606') + '</span>';
  }
  html += '</span>';
  return html;
}

function initStarRatings() {
  // Read-only displays
  document.querySelectorAll('.star-display-slot').forEach(function(el) {
    var r = parseInt(el.dataset.rating) || 0;
    el.innerHTML = createStarDisplay(r);
  });

  // Interactive ratings
  document.querySelectorAll('.star-rating-interactive').forEach(function(el) {
    var malId = el.dataset.malId;
    var current = parseInt(el.dataset.currentRating) || 0;
    var actionUrl = el.dataset.actionUrl;
    renderInteractiveStars(el, malId, current, actionUrl);
  });
}

function renderInteractiveStars(container, malId, currentRating, actionUrl) {
  container.innerHTML = '';
  var wrap = document.createElement('div');
  wrap.className = 'star-rating';
  for (var i = 5; i >= 1; i--) {
    (function(score) {
      var star = document.createElement('button');
      star.type = 'button';
      star.className = 'star-rating__star' + (score <= currentRating ? ' filled' : '');
      star.textContent = score <= currentRating ? '\u2605' : '\u2606';
      star.title = score + ' star' + (score !== 1 ? 's' : '');
      star.addEventListener('click', function() {
        // Submit rating via form
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = actionUrl;
        form.style.display = 'none';
        var idField = document.createElement('input');
        idField.name = 'anime_id';
        idField.value = malId;
        var rField = document.createElement('input');
        rField.name = 'user_rating';
        rField.value = score;
        var sField = document.createElement('input');
        sField.name = 'status';
        sField.value = 'completed';
        form.appendChild(idField);
        form.appendChild(rField);
        form.appendChild(sField);
        document.body.appendChild(form);
        form.submit();
      });
      wrap.appendChild(star);
    })(i);
  }
  container.appendChild(wrap);
}

document.addEventListener('DOMContentLoaded', initStarRatings);

/* ── Swipe Cards ───────────────────────────────────────────────────── */
var SwipeManager = {
  cards: [],
  currentIndex: 0,
  startX: 0,
  startY: 0,
  currentX: 0,
  isDragging: false,
  threshold: 80,

  init: function() {
    var area = document.querySelector('.swipe-area');
    if (!area) return;
    this.area = area;
    this.cards = Array.from(area.querySelectorAll('.swipe-card'));
    this.currentIndex = 0;
    this.setupCards();
    this.bindEvents();
  },

  setupCards: function() {
    for (var i = 0; i < this.cards.length; i++) {
      var card = this.cards[i];
      if (i < this.currentIndex) {
        card.style.display = 'none';
      } else if (i === this.currentIndex) {
        card.style.transform = '';
        card.style.opacity = '1';
        card.style.zIndex = this.cards.length - i;
      } else {
        card.style.transform = 'scale(' + (1 - (i - this.currentIndex) * 0.03) + ')';
        card.style.opacity = i - this.currentIndex > 2 ? '0' : '1';
        card.style.zIndex = this.cards.length - i;
      }
    }
  },

  bindEvents: function() {
    var self = this;
    // Touch
    this.area.addEventListener('touchstart', function(e) { self.onStart(e.touches[0].clientX, e.touches[0].clientY); }, {passive: true});
    this.area.addEventListener('touchmove', function(e) { self.onMove(e.touches[0].clientX, e.touches[0].clientY); }, {passive: false});
    this.area.addEventListener('touchend', function() { self.onEnd(); });
    // Mouse
    this.area.addEventListener('mousedown', function(e) { e.preventDefault(); self.onStart(e.clientX, e.clientY); });
    document.addEventListener('mousemove', function(e) { if (self.isDragging) self.onMove(e.clientX, e.clientY); });
    document.addEventListener('mouseup', function() { if (self.isDragging) self.onEnd(); });
    // Keyboard
    document.addEventListener('keydown', function(e) {
      if (!document.querySelector('.swipe-area')) return;
      if (e.key === 'ArrowLeft') { e.preventDefault(); self.swipeLeft(); }
      if (e.key === 'ArrowRight') { e.preventDefault(); self.swipeRight(); }
    });
    // Buttons
    var skipBtn = document.querySelector('.swipe-btn--skip');
    var addBtn  = document.querySelector('.swipe-btn--add');
    if (skipBtn) skipBtn.addEventListener('click', function() { self.swipeLeft(); });
    if (addBtn)  addBtn.addEventListener('click', function() { self.swipeRight(); });
  },

  onStart: function(x, y) {
    if (this.currentIndex >= this.cards.length) return;
    this.isDragging = true;
    this.startX = x;
    this.startY = y;
    this.currentX = 0;
    var card = this.cards[this.currentIndex];
    card.classList.add('dragging');
  },

  onMove: function(x, y) {
    if (!this.isDragging) return;
    this.currentX = x - this.startX;
    var card = this.cards[this.currentIndex];
    var rotate = this.currentX * 0.08;
    card.style.transform = 'translateX(' + this.currentX + 'px) rotate(' + rotate + 'deg)';

    // Show hints
    var skipHint = card.querySelector('.swipe-hint--skip');
    var addHint  = card.querySelector('.swipe-hint--add');
    if (skipHint) skipHint.style.opacity = this.currentX < -30 ? Math.min(1, (-this.currentX - 30) / 50) : 0;
    if (addHint)  addHint.style.opacity  = this.currentX > 30 ? Math.min(1, (this.currentX - 30) / 50) : 0;
  },

  onEnd: function() {
    if (!this.isDragging) return;
    this.isDragging = false;
    var card = this.cards[this.currentIndex];
    card.classList.remove('dragging');

    if (this.currentX > this.threshold) {
      this.completeSwipe('right');
    } else if (this.currentX < -this.threshold) {
      this.completeSwipe('left');
    } else {
      // Snap back
      card.style.transform = '';
      var skipHint = card.querySelector('.swipe-hint--skip');
      var addHint  = card.querySelector('.swipe-hint--add');
      if (skipHint) skipHint.style.opacity = 0;
      if (addHint)  addHint.style.opacity  = 0;
    }
  },

  swipeLeft: function() {
    if (this.currentIndex >= this.cards.length) return;
    this.completeSwipe('left');
  },

  swipeRight: function() {
    if (this.currentIndex >= this.cards.length) return;
    this.completeSwipe('right');
  },

  completeSwipe: function(direction) {
    var card = this.cards[this.currentIndex];
    var malId = card.dataset.malId;

    if (direction === 'right') {
      card.classList.add('exit-right');
      // Add to watched
      var addUrl = card.dataset.addUrl;
      if (addUrl) {
        fetch(addUrl, {method: 'GET', credentials: 'same-origin'}).catch(function(){});
      }
    } else {
      card.classList.add('exit-left');
    }

    this.currentIndex++;

    // Update remaining stack
    var self = this;
    setTimeout(function() {
      self.setupCards();
      // Check if we need more cards
      if (self.currentIndex >= self.cards.length - 2) {
        self.loadMore();
      }
      if (self.currentIndex >= self.cards.length) {
        self.showEmpty();
      }
    }, 400);
  },

  loadMore: function() {
    var self = this;
    var nextOffset = parseInt(this.area.dataset.offset || 0) + 50;
    var ranking = this.area.dataset.ranking || 'all';
    var apiUrl = this.area.dataset.apiUrl + '?ranking=' + ranking + '&offset=' + nextOffset;

    fetch(apiUrl, {credentials: 'same-origin'})
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data || !data.length) return;
        self.area.dataset.offset = nextOffset;
        data.forEach(function(anime) {
          var card = self.createCard(anime);
          self.area.appendChild(card);
          self.cards.push(card);
        });
        self.setupCards();
      })
      .catch(function(){});
  },

  createCard: function(anime) {
    var card = document.createElement('div');
    card.className = 'swipe-card';
    card.dataset.malId = anime.mal_id || anime.id;
    card.dataset.addUrl = this.area.dataset.addBase.replace('0', card.dataset.malId).replace('STATUS', 'completed');

    var imgUrl = '';
    if (anime.main_picture) imgUrl = anime.main_picture.large || anime.main_picture.medium || '';
    else if (anime.images && anime.images.jpg) imgUrl = anime.images.jpg.image_url || '';

    card.innerHTML =
      '<img class="swipe-card__img" src="' + imgUrl + '" alt="">' +
      '<div class="swipe-card__gradient"></div>' +
      '<div class="swipe-hint swipe-hint--skip">SKIP</div>' +
      '<div class="swipe-hint swipe-hint--add">ADD</div>' +
      '<div class="swipe-card__info">' +
        '<div class="swipe-card__title">' + (anime.title || 'Unknown') + '</div>' +
        '<div class="swipe-card__meta">' +
          (anime.episodes ? '<span class="swipe-card__badge">' + anime.episodes + ' eps</span>' : '') +
          (anime.score ? '<span class="swipe-card__badge swipe-card__badge--score">\u2605 ' + anime.score + '</span>' : '') +
        '</div>' +
      '</div>';

    return card;
  },

  showEmpty: function() {
    var existing = this.area.querySelector('.discover-empty');
    if (existing) return;
    var empty = document.createElement('div');
    empty.className = 'discover-empty';
    empty.innerHTML = '<p style="font-family:Playfair Display,serif;font-style:italic;font-size:18px;color:#444">No more anime to discover</p>' +
      '<p style="color:#333;font-size:11px;margin-top:8px">Try a different category or search for something specific</p>';
    this.area.style.aspectRatio = 'auto';
    this.area.appendChild(empty);
  }
};

document.addEventListener('DOMContentLoaded', function() { SwipeManager.init(); });

/* ── Auto-dismiss flash ──────────────────────────────────────────────── */
setTimeout(function() {
  document.querySelectorAll('.flash').forEach(function(f) {
    f.style.transition = 'opacity .4s';
    f.style.opacity = '0';
    setTimeout(function() { f.remove(); }, 400);
  });
}, 3500);
