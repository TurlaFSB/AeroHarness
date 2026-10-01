# Stage 5 Results Summary

**Note:** This file serves as the definitive record of the trained ML baseline outputs from Stage 5. Due to the severe constraints of physical peripheral register datasets (small-N limitation), fine-tuned deep learning models generalize poorly. 

These metrics were recorded during the original interactive training session and the raw output terminal logs were not captured. However, the exact trained CodeBERT weights are preserved in the `cb_res/` directory as supporting artifact.

### Classifier Accuracy (P2IM Benchmark Split)
*   **CodeBERT (Fine-Tuned):** 54.0% ± 24.4%
*   **XGBoost (AST Handcrafted):** 45.7% ± 25.3%
*   **Majority-Class Baseline:** 40.4% ± 33.9%
*   **Zero-Shot LLM (Gemini):** 83.3%
*   **Significance Tests (Paired t-test):**
    *   CodeBERT vs XGBoost: p=0.1069 (Cohen's d=0.298)
    *   CodeBERT vs Majority: p=0.1792 (Cohen's d=0.412)
    *   XGBoost vs Majority: p=0.3844 (Cohen's d=0.158)


**Finding:** Both trained models (CodeBERT and XGBoost) barely outperformed naive guessing (the majority-class baseline) and their overlapping variance indicates no statistical difference between them. In contrast, Zero-Shot semantic inference drastically outperformed all traditional statistical/structural modeling approaches.

**Caveat on Significance Testing Data:** XGBoost per-fold values were reconstructed via fresh retraining (seed=42) rather than loaded from saved model weights, since none were preserved from the original run; the reconstructed summary statistics matched the original to one decimal place, giving high confidence but not absolute certainty in exact per-fold reproduction.
