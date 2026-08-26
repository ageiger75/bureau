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

  document.addEventListener("DOMContentLoaded", function () {
    wireConfirmations();
    openTargetSection();
    wireClaimForms();
    wireUnsavedGuard();
  });
})();
