import torch
import pandas as pd
import numpy as np
from torch import Tensor


class MultiConfusionMatrix:
    """Confusion Matrix for Multiple Models. It will generage n_models confusion matrix of n_classes x n_classes.
    Rows = Ground Truth, Cols = Predictions
    """

    def __init__(
        self,
        n_models: int,
        n_classes: int,
        device: str = "cpu",
        model_ids: Tensor = None,
    ) -> None:
        self.n_models = n_models
        self.n_classes = n_classes
        self.model_ids = model_ids
        self.cm = torch.zeros(
            (self.n_models, self.n_classes, self.n_classes),
            device=device,
            dtype=torch.int,
        )
        self.n_models_arange = torch.arange(
            self.n_models, device=device, dtype=torch.long
        )
        self.one = torch.tensor([1], device=device, dtype=torch.int)
        self.device = device

    def update(self, predictions: Tensor, targets: Tensor) -> None:
        """Updates the Confuson Matrix

        Args:
                predictions (Tensor): [batch_size, n_models]
                targets (Tensor): [batch_size]
        """
        with torch.inference_mode():
            if predictions.ndim > 2:
                predictions = predictions.argmax(-1)

            if predictions.device != self.cm.device:
                predictions = predictions.to(self.cm.device)

            self.cm.index_put_(
                indices=(self.n_models_arange, targets[:, None], predictions),
                values=self.one,
                accumulate=True,
            )

    def calculate_metrics(self):
        metrics = {}
        self.total_samples = self.cm[0].sum()

        self.tp = self.cm.diagonal(dim1=-1, dim2=-2)
        self.fn = self.cm.sum(-1) - self.tp
        self.fp = self.cm.sum(-2) - self.tp
        self.tn = self.total_samples - self.fn - self.fp - self.tp
        metrics["overall_acc"] = self.tp.sum(-1) / self.total_samples
        metrics["matthews_corrcoef"] = self._matthews_corrcoef()

        return metrics

    def to_dataframe(self, prefix=None):
        df = pd.DataFrame(self.calculate_metrics())
        if prefix is not None:
            df.columns = [f"{prefix}{c}" for c in df.columns]
        if self.model_ids is not None:
            df["model_id"] = self.model_ids.cpu().numpy()
            df = df.set_index("model_id")

        return df

    def _matthews_corrcoef(self):
        numerator = self.tp * self.tn - self.fp * self.fn
        denominator = torch.sqrt(
            (self.tp + self.fp)
            * (self.tp + self.fn)
            * (self.tn + self.fp)
            * (self.tn + self.fn)
        )
        matt = numerator / denominator
        C = self.cm
        # C = confusion_matrix(y_true, y_pred, sample_weight=sample_weight)
        t_sum = C.sum(dim=-1)
        p_sum = C.sum(dim=-2)
        n_correct = self.tp.sum(-1)
        cov_ytyp = n_correct * self.total_samples - (t_sum * p_sum).sum(
            -1
        )  # torch.dot(t_sum, p_sum)
        cov_ypyp = self.total_samples ** 2 - (p_sum * p_sum).sum(
            -1
        )  # torch.dot(p_sum, p_sum)
        cov_ytyt = self.total_samples ** 2 - (t_sum * t_sum).sum(
            -1
        )  # torch.dot(t_sum, t_sum)

        matt = cov_ytyp / torch.sqrt(cov_ytyt * cov_ypyp)
        invalid_mask = (cov_ypyp * cov_ytyt) == 0

        matt[invalid_mask] = 0.000000001

        return matt