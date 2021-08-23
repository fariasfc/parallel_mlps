#!/usr/bin/env python


from torch.functional import Tensor
from parallel_mlps.autoconstructive.model.parallel_mlp import (
    ParallelMLPs,
    build_model_ids,
)
import pytest
import torch
from torch import nn
from torch.optim import Adam

"""Tests for `parallel_mlps` package."""
import random
import torch
import os


# Reproducibility:
def reproducibility():
    torch.manual_seed(0)
    random.seed(0)
    # torch.set_deterministic(True)
    # torch.use_deterministic_algorithms(True)
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":16:8"


reproducibility()

N_SAMPLES = 5
N_FEATURES = 3
N_OUTPUTS = 2

MIN_NEURONS = 1
MAX_NEURONS = 3


@pytest.fixture
def X():
    return torch.rand(size=(N_SAMPLES, N_FEATURES))


@pytest.fixture
def Y():
    return torch.randint(low=0, high=2, size=(N_SAMPLES,))


@pytest.fixture
def activation_functions():
    return [nn.LeakyReLU(), nn.Sigmoid()]


@pytest.fixture
def parallel_mlp_object(activation_functions, X):
    layer_ids = build_model_ids(
        repetitions=3,
        activation_functions=activation_functions,
        min_neurons=MIN_NEURONS,
        max_neurons=MAX_NEURONS,
        step=1,
    )

    return ParallelMLPs(
        in_features=X.shape[1],
        out_features=N_OUTPUTS,
        bias=True,
        hidden_neuron__model_id=layer_ids,
        activations=activation_functions,
    )


@pytest.mark.parametrize(
    "activation_functions,repetitions,min_neurons,max_neurons,step,expected",
    [
        (
            [nn.ReLU(), nn.Sigmoid()],
            3,
            MIN_NEURONS,
            MAX_NEURONS,
            1,
            # fmt: off
            [0, 1, 1, 2, 2, 2, 3, 4, 4, 5, 5, 5, 6, 7, 7, 8, 8, 8, 9, 10, 10, 11, 11, 11, 12, 13, 13, 14, 14, 14, 15, 16, 16, 17, 17, 17, ],
            # fmt: on
        ),
        (
            [nn.ReLU(), nn.Sigmoid()],
            3,
            MIN_NEURONS,
            MAX_NEURONS,
            2,
            # fmt: off
            [0, 1, 1, 1, 2, 3, 3, 3, 4, 5, 5, 5, 6, 7, 7, 7, 8, 9, 9, 9, 10, 11, 11, 11],
            # fmt: on
        ),
        (
            [nn.ReLU(), nn.Sigmoid()],
            3,
            MAX_NEURONS,
            MAX_NEURONS,
            1,
            # fmt: off
            [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5]
            # fmt: on
        ),
        (
            [nn.ReLU(), nn.Sigmoid()],
            3,
            2,
            4,
            2,
            # fmt: off
            [0, 0, 1, 1, 1, 1, 2, 2, 3, 3, 3, 3, 4, 4, 5, 5, 5, 5, 6, 6, 7, 7, 7, 7, 8, 8, 9, 9, 9, 9, 10, 10, 11, 11, 11, 11]
            # fmt: on
        ),
        (
            [nn.ReLU(), nn.Tanh(), nn.Sigmoid()],
            2,
            2,
            4,
            2,
            # fmt: off
            [0, 0, 1, 1, 1, 1, 2, 2, 3, 3, 3, 3, 4, 4, 5, 5, 5, 5, 6, 6, 7, 7, 7, 7, 8, 8, 9, 9, 9, 9, 10, 10, 11, 11, 11, 11]
            # fmt: on
        ),
    ],
)
def test_build_model_ids(
    activation_functions, repetitions, min_neurons, max_neurons, step, expected
):
    layers_ids = build_model_ids(
        repetitions=repetitions,
        activation_functions=activation_functions,
        min_neurons=min_neurons,
        max_neurons=max_neurons,
        step=step,
    )

    assert expected == layers_ids
    print(layers_ids)


def test_fail_build_model_ids():
    with pytest.raises(ValueError, match=r".*only unique values.*"):
        build_model_ids(
            repetitions=2,
            activation_functions=[nn.ReLU(), nn.Sigmoid(), nn.Sigmoid()],
            min_neurons=MIN_NEURONS,
            max_neurons=MAX_NEURONS,
            step=1,
        )

    with pytest.raises(ValueError, match=r".*nn.Identity().*"):
        build_model_ids(
            repetitions=2,
            activation_functions=[],
            min_neurons=MIN_NEURONS,
            max_neurons=MAX_NEURONS,
            step=1,
        )


def test_parallel_single_mlps_forward(parallel_mlp_object: ParallelMLPs, X: Tensor):
    output = parallel_mlp_object(X)
    for i in parallel_mlp_object.unique_model_ids:
        mlp = parallel_mlp_object.extract_mlp(i)
        output_mlp = mlp(X)
        assert torch.allclose(output[:, i, :], output_mlp)


def test_trainings(X, Y, parallel_mlp_object: ParallelMLPs):
    reproducibility()
    lr = 1
    atol = 1e-8
    rtol = 0.99
    parallel_optimizer = Adam(params=parallel_mlp_object.parameters(), lr=lr)

    single_models = [
        parallel_mlp_object.extract_mlp(i) for i in parallel_mlp_object.unique_model_ids
    ]
    single_optimizers = [
        Adam(params=model.parameters(), lr=lr) for model in single_models
    ]

    num_epochs = 100
    parallel_loss = nn.CrossEntropyLoss(reduction="none")
    sequential_loss = nn.CrossEntropyLoss()

    X = X.to(parallel_mlp_object.device)
    Y = Y.to(parallel_mlp_object.device)
    gradient = torch.ones(parallel_mlp_object.num_unique_models).to(X.device)

    for e in range(num_epochs):
        print(f"Epoch: {e}")
        parallel_optimizer.zero_grad()
        outputs = parallel_mlp_object(X)
        per_sample_candidate_losses = parallel_mlp_object.calculate_loss(
            parallel_loss, outputs, Y
        )
        candidate_losses = per_sample_candidate_losses.mean(0)
        candidate_losses.backward(gradient=gradient)
        parallel_optimizer.step()
        print(candidate_losses)
        print(parallel_mlp_object.hidden_layer.weight.mean())

        for i, (model, optimizer) in enumerate(zip(single_models, single_optimizers)):
            optimizer.zero_grad()
            single_outputs = model(X)
            loss = sequential_loss(single_outputs, Y)
            loss.backward()
            optimizer.step()

            # Asserts
            assert torch.allclose(candidate_losses[i], loss, atol=atol, rtol=rtol)

            m = parallel_mlp_object.extract_mlp(i)
            # assert torch.allclose(m[0].weight, model[0].weight, atol=atol, rtol=rtol)
            assert type(m[1]) == type(model[1])
            # assert torch.allclose(m[2].weight, model[2].weight, atol=atol, rtol=rtol)


@pytest.fixture
def response():
    """Sample pytest fixture.

    See more at: http://doc.pytest.org/en/latest/fixture.html
    """
    # import requests
    # return requests.get('https://github.com/audreyr/cookiecutter-pypackage')


def test_content(response):
    """Sample pytest test function with the pytest fixture as an argument."""
    # from bs4 import BeautifulSoup
    # assert 'GitHub' in BeautifulSoup(response.content).title.string
