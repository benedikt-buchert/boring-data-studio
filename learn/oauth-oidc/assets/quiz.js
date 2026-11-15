// Quiz component. Markup:
// <div class="quiz"> <div class="q" data-answer="2"> <p class="q-prompt">…</p>
//   <div class="q-opts"><button class="q-opt">…</button>×N</div>
//   <p class="q-explain" hidden>…</p> </div> … <p class="quiz-score" hidden></p> </div>
// data-answer is the 0-based index of the right option. One try per question.
(function () {
  document.querySelectorAll(".quiz").forEach(function (quiz) {
    var qs = quiz.querySelectorAll(".q"), done = 0, right = 0;
    var score = quiz.querySelector(".quiz-score");
    qs.forEach(function (q) {
      var answer = Number(q.dataset.answer);
      var opts = q.querySelectorAll(".q-opt");
      var explain = q.querySelector(".q-explain");
      opts.forEach(function (btn, i) {
        btn.type = "button";
        btn.addEventListener("click", function () {
          opts.forEach(function (b) { b.disabled = true; });
          opts[answer].classList.add("is-right");
          if (i !== answer) btn.classList.add("is-wrong"); else right++;
          if (explain) explain.hidden = false;
          done++;
          if (score && done === qs.length) {
            score.hidden = false;
            score.textContent = right + " of " + qs.length + " right. " +
              (right === qs.length ? "Come back in two days and try the recall prompts without looking." :
               "Reread the section on the ones you missed, then ask your teacher about them.");
          }
        });
      });
    });
  });
})();
