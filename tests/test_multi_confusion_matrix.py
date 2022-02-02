import pytest
from pycm import ConfusionMatrix
import pycm
import torch
from parallel_mlps.autoconstructive.utils.multi_confusion_matrix import (
    MultiConfusionMatrix,
)

torch.manual_seed(42)


def test_multi_confusion_matrix():
    batch_size = 8
    n_classes = 2
    n_models = 5

    predictions = torch.rand((batch_size, n_models, n_classes))
    predictions = predictions.argmax(-1)
    targets = torch.arange(batch_size) % n_classes

    predictions = torch.tensor(
        [
            [0, 0, 1, 1, 0],
            [0, 0, 1, 0, 1],
            [0, 0, 1, 0, 0],
            [0, 0, 1, 1, 0],
            [1, 1, 0, 0, 0],
            [1, 1, 1, 0, 0],
            [0, 0, 0, 0, 0],
            [1, 0, 1, 1, 1],
            [1, 0, 1, 0, 1],
        ]
    )

    targets = torch.tensor([0, 0, 0, 0, 1, 1, 0, 1, 1])
    expected_cm = torch.tensor(
        [
            [[5, 0], [0, 4]],
            [[5, 0], [2, 2]],
            [[1, 4], [1, 3]],
            [[3, 2], [3, 1]],
            [[4, 1], [2, 2]],
        ]
    ).int()

    mcm = MultiConfusionMatrix(n_models, n_classes)
    mcm.update(predictions, targets)

    print(predictions)
    print(targets)

    cm = torch.zeros((n_models, n_classes, n_classes)).int()

    cm.index_put_(
        indices=(torch.arange(n_models), targets[:, None], predictions),
        values=torch.Tensor([1]).int(),
        accumulate=True,
    )
    print(cm)
    print(expected_cm)
    assert torch.equal(cm, expected_cm)
    assert torch.equal(expected_cm, mcm.cm)


def test_multi_confusion_matrix_3d():
    batch_size = 8
    n_classes = 3
    n_models = 5

    predictions = torch.rand((batch_size, n_models, n_classes))
    predictions = predictions.argmax(-1)
    targets = torch.arange(batch_size) % n_classes

    predictions = torch.tensor(
        [
            [0, 0, 1, 1, 2],
            [2, 0, 1, 0, 2],
            [2, 0, 1, 2, 2],
            [0, 0, 1, 1, 2],
            [1, 1, 0, 0, 1],
            [1, 1, 1, 0, 1],
            [0, 0, 0, 0, 0],
            [1, 2, 1, 1, 0],
            [1, 0, 1, 0, 1],
        ]
    )

    targets = torch.tensor([0, 2, 2, 0, 1, 1, 0, 1, 1])
    expected_cm = torch.tensor(
        [
            [[3, 0, 0], [0, 4, 0], [0, 0, 2]],
            [[3, 0, 0], [1, 2, 1], [2, 0, 0]],
            [[1, 2, 0], [1, 3, 0], [0, 2, 0]],
            [[1, 2, 0], [3, 1, 0], [1, 0, 1]],
            [[1, 0, 2], [1, 3, 0], [0, 0, 2]],
        ]
    ).int()

    mcm = MultiConfusionMatrix(n_models, n_classes)
    mcm.update(predictions[: batch_size // 2], targets[: batch_size // 2])
    mcm.update(predictions[batch_size // 2 :], targets[batch_size // 2 :])

    print(predictions)
    print(targets)

    cm = torch.zeros((n_models, n_classes, n_classes)).int()

    cm.index_put_(
        indices=(torch.arange(n_models), targets[:, None], predictions),
        values=torch.Tensor([1]).int(),
        accumulate=True,
    )
    print(cm)
    print(expected_cm)
    assert torch.equal(cm, expected_cm)
    assert torch.equal(cm, mcm.cm)


def test_pycm_equivalence():
    n_classes = 3
    n_models = 5
    batch_size = 32
    torch.manual_seed(42)
    predictions = torch.rand(batch_size, n_models, n_classes).argmax(-1)
    targets = torch.arange(batch_size) % n_classes

    multi_cm = MultiConfusionMatrix(n_models, n_classes, "cpu")
    multi_cm.update(predictions, targets)

    multi_cm_metrics = multi_cm.calculate_metrics()
    for model_id in range(n_models):
        cm = ConfusionMatrix(targets.numpy(), predictions.numpy()[:, model_id])
        assert cm.Overall_ACC == multi_cm_metrics["overall_acc"][model_id]
        for c in range(n_classes):
            assert multi_cm.tp[model_id][c] == cm.TP[c]
            assert multi_cm.fp[model_id][c] == cm.FP[c]
            assert multi_cm.tn[model_id][c] == cm.TN[c]
            assert multi_cm.fn[model_id][c] == cm.FN[c]