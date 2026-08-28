/* CEO OS — Decision Room
   JavaScript vanilla, aucune dépendance, aucun appel réseau.
   La CSP interdit les gestionnaires en ligne (onclick, onsubmit) : tout passe par
   addEventListener. L'application reste entièrement utilisable sans ce fichier —
   lire, saisir et enregistrer un dossier ne dépend pas de JavaScript. */

(function () {
  "use strict";

  /* --- Confirmation des actions destructrices ---------------------------- */

  function wireConfirmations() {
    var buttons = document.querySelectorAll("[data-confirm]");
    Array.prototype.forEach.call(buttons, function (button) {
      button.addEventListener("click", function (event) {
        if (!window.confirm(button.getAttribute("data-confirm"))) {
          event.preventDefault();
        }
      });
    });
  }

  /* --- Ouverture de la section visée par l'ancre ------------------------- */

  function openTargetSection() {
    if (!window.location.hash) {
      return;
    }
    var target = document.querySelector(window.location.hash);
    if (!target) {
      return;
    }
    var node = target;
    while (node && node !== document.body) {
      if (node.tagName === "DETAILS") {
        node.open = true;
      }
      node = node.parentNode;
    }
    target.scrollIntoView();
  }

  /* --- Avertissement « fait sans source », à la saisie -------------------
     Même politique que le serveur : on signale, on ne bloque pas. L'intérêt de le
     faire aussi côté client est que le message arrive avant l'enregistrement,
     au moment où la source est encore en mémoire de celui qui écrit. */

  var UNSOURCED_MESSAGE =
    "Présenté comme un fait, mais sans source. Ce sera enregistré et signalé sur le dossier.";

  function wireClaimForms() {
    var forms = document.querySelectorAll("form[action*='/claims']");
    Array.prototype.forEach.call(forms, function (form) {
      var category = form.querySelector("select[name='category']");
      var source = form.querySelector("input[name='source_ref']");
      if (!category || !source) {
        return;
      }

      var notice = document.createElement("p");
      notice.className = "field-warning";
      notice.hidden = true;
      notice.textContent = UNSOURCED_MESSAGE;
      source.parentNode.appendChild(notice);

      function refresh() {
        var isFact = category.value === "sourced_fact";
        var hasSource = source.value.trim().length > 0;
        notice.hidden = !(isFact && !hasSource);
      }

      category.addEventListener("change", refresh);
      source.addEventListener("input", refresh);
      refresh();
    });
  }

  /* --- Garde-fou de sortie ----------------------------------------------
     Un dossier est un travail long : quitter la page en perdant un texte saisi est
     une perte réelle. On ne surveille que les formulaires réellement modifiés. */

  function wireUnsavedGuard() {
    var dirty = false;

    var forms = document.querySelectorAll("form");
    Array.prototype.forEach.call(forms, function (form) {
      form.addEventListener("input", function () {
        dirty = true;
      });
      form.addEventListener("submit", function () {
        dirty = false;
      });
    });

    window.addEventListener("beforeunload", function (event) {
      if (!dirty) {
        return undefined;
      }
      event.preventDefault();
      event.returnValue = "";
      return "";
    });
  }

  /* --- La page attend ses chiffres frais toute seule ---------------------
     L'écran s'ouvre sur la dernière lecture et la nouvelle arrive derrière, quelques
     minutes plus tard. Le seul signe en était une ligne dans la fenêtre du serveur,
     donc la consigne était « surveiller le journal et recharger » : une habitude de
     développeur transmise à un lecteur, et elle n'était pas suivie parce qu'elle n'a
     pas à l'être.

     On interroge un point d'entrée qui ne lit que le cache — il ne peut pas déclencher
     de requête vers l'entrepôt, une vérification de fraîcheur qui coûterait trois
     minutes serait pire que le problème qu'elle règle. On s'arrête au bout de dix
     minutes : passé ce délai, la lecture a échoué et recharger n'y changera rien. */

  var FRESHNESS_EVERY_MS = 5000;
  var FRESHNESS_FOR_MS = 600000;

  function watchForFreshFigures() {
    var header = document.querySelector("[data-read-at]");
    var line = document.getElementById("freshness-line");
    if (!header || !window.fetch) {
      return;
    }
    var shown = header.getAttribute("data-read-at");
    if (!shown) {
      return;
    }
    var startedAt = Date.now();

    var timer = window.setInterval(function () {
      if (Date.now() - startedAt > FRESHNESS_FOR_MS) {
        window.clearInterval(timer);
        return;
      }
      window.fetch("/freshness", { headers: { Accept: "application/json" } })
        .then(function (response) { return response.json(); })
        .then(function (body) {
          if (body && body.as_of && body.as_of !== shown) {
            window.clearInterval(timer);
            /* Dit avant de recharger : une page qui se remplace sans prévenir pendant
               qu'on la lit est déroutante, même quand elle a raison de le faire. */
            if (line) {
              line.textContent = "Chiffres plus récents disponibles — rechargement…";
            }
            window.setTimeout(function () { window.location.reload(); }, 1200);
          }
        })
        .catch(function () { /* Le serveur s'arrête : rien à signaler, rien à faire. */ });
    }, FRESHNESS_EVERY_MS);
  }

  document.addEventListener("DOMContentLoaded", function () {
    watchForFreshFigures();
    wireConfirmations();
    openTargetSection();
    wireClaimForms();
    wireUnsavedGuard();
  });
})();
