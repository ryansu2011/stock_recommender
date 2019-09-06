import math
import pickle as pk
import numpy as np
from matplotlib import pyplot as plt
import tensorflow as tf
import utility
from models import get_batch_input_array
from sklearn.model_selection import train_test_split


@utility.single_instance_generator
def next_color():
    """
    Generate the next color code for plotting.
    This function is decorated by single_instance_generator.
    It behaves like a singleton object with interperter level lifespan
    Just call next_color() to get the color string.
    """
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    while True:
        for color in color_cycle:
            yield color


def get_accuracy_matrix(trained_model, x_test, y_test, threshold: float):
    """
    :param trained_model: keras model
    :param x_test: ndarray
    :param y_test: ndarray, real data
    :param threshold: the prediction will be categorized into 3 groups: [-inf ... -threhold ... +threhold ... +inf]
    :return: a 3x3 2d list. axis-0 is the predicted result, axis-1 is y_test result
    """
    y_predict = trained_model.predict(x_test).reshape(-1)
    y_real = y_test.reshape(-1)
    y_predict = (y_predict > threshold) + 1 - (y_predict < -threshold)
    y_real = (y_real > threshold) + 1 - (y_real < -threshold)
    ret = np.zeros(shape=(3, 3), dtype=int)
    for yp, yr in zip(y_predict, y_real):
        ret[yp][yr] += 1
    return ret


def get_data(load_from_file=False, separate_input=False):
    """
    :param load_from_file: bool, if True, read the pk file for faster performance. If False, read the raw json file.
    :param separate_input: how to treat axis-2 in X_train and X_test.
        If True:    shape of X is: (num_sample, time_seq_length, 5). 5 means SMA of 1, 5, 20, 100, 200 days SMA
        If False:   return a list of 5 ndarrays, each have dimension (num_sample, time_seq_length, 1).
                    this is used for multiple input pipes
    :return: 4 ndarrays
        x_train     shape = see below
        x_test      shape = see below
        y_train     shape = (num_sample, 1)
        y_test      shape = (num_test, 1)
    """

    if load_from_file:
        with open("x_train.pk", "rb") as fp:
            x_train = pk.load(fp)
        with open("x_test.pk", "rb") as fp:
            x_test = pk.load(fp)
        with open("y_train.pk", "rb") as fp:
            y_train = pk.load(fp)
        with open("y_test.pk", "rb") as fp:
            y_test = pk.load(fp)

        if separate_input:
            x_train = [x_train[:, :, 0:1],
                       x_train[:, :, 1:2],
                       x_train[:, :, 2:3],
                       x_train[:, :, 3:4],
                       x_train[:, :, 4:5]]
            x_test = [x_test[:, :, 0:1],
                      x_test[:, :, 1:2],
                      x_test[:, :, 2:3],
                      x_test[:, :, 3:4],
                      x_test[:, :, 4:5]]
        return x_train, x_test, y_train, y_test

    x_total, y_total = next(get_batch_input_array(batch_size=-1, sample_offset=5, year_cutoff=20))
    x_train, x_test, y_train, y_test = train_test_split(x_total, y_total, test_size=0.2, random_state=123)
    with open("x_train.pk", "wb") as fp:
        pk.dump(x_train, fp)
    with open("x_test.pk", "wb") as fp:
        pk.dump(x_test, fp)
    with open("y_train.pk", "wb") as fp:
        pk.dump(y_train, fp)
    with open("y_test.pk", "wb") as fp:
        pk.dump(y_test, fp)

    if separate_input:
        x_train = [x_train[:, :, 0:1],
                   x_train[:, :, 1:2],
                   x_train[:, :, 2:3],
                   x_train[:, :, 3:4],
                   x_train[:, :, 4:5]]
        x_test = [x_test[:, :, 0:1],
                  x_test[:, :, 1:2],
                  x_test[:, :, 2:3],
                  x_test[:, :, 3:4],
                  x_test[:, :, 4:5]]

    return x_train, x_test, y_train, y_test


def save(model):
    """
    Save weight parameters with model name (from model.cname, set by @named_model decorator)
    """
    weight_file = "model_weights\\" + model.cname
    model.save_weights(weight_file)


def load(model):
    """
    Load weight parameters from file (file name is from model.cname, set by @named_model decorator)
    """
    weight_file = "model_weights\\" + model.cname
    model.load_weights(weight_file)


def train(model, epochs, x_train, x_test, y_train, y_test, save_weight=False):

    # cb1 = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=20)
    history = model.fit(x_train,
                        y_train,
                        epochs=epochs,
                        batch_size=1500,
                        validation_data=(x_test, y_test),
                        use_multiprocessing=True,
                        verbose=1)
    # par callbacks = [cb1, cb2],
    if save_weight:
        save(model)
    return history


def evaluate(models, xx, yy, output_file_name, cutoff=5.0):
    """
    Evaluate model by 3x3 accuracy matrix. +cutoff and -cutoff are separation point to get the three ranges
    Cutoff unit is in percentage, different from unit of yy. YY is between (-1, 1).
        Cutoff_in_YY_unit = tanh(Cutoff * 0.1)
    """
    if type(models) is not list:
        models = [models]
    cutoff = math.tanh(cutoff * 0.1)
    with open(output_file_name + ".txt", "w") as fp:
        for model in models:
            fp.write("Model name: %s \n\n" % model.cname)
            accuracy_matrix = get_accuracy_matrix(model, xx, yy, cutoff)
            score = accuracy_matrix[0][0] + accuracy_matrix[2][2] - accuracy_matrix[2][0] - accuracy_matrix[0][2]
            score = float(score) / float(sum(accuracy_matrix[0]) + sum(accuracy_matrix[2]))
            fp.write(str(accuracy_matrix))
            fp.write("\n\nScore = %f \n\n\n\n" % score)


def plot_history(history, models, name=""):
    if len(name) > 0 and name[len(name) - 1] != "-":
        name = name + "-"
    if type(history) is not list:
        history = [history]
        models = [models]
    for hist, model in zip(history, models):
        color = next_color()
        plt.plot(hist.epoch, hist.history["mae"], label=(model.cname+"-train"), color=color, linestyle="dashed")
        plt.plot(hist.epoch, hist.history["val_mae"], label=(model.cname+"-val"), color=color, linestyle="solid")
    plt.title(name+"mae")
    plt.legend()
    plt.savefig(name+"mae.svg")
    plt.close()
    for hist, model in zip(history, models):
        color = next_color()
        plt.plot(hist.epoch, hist.history["mse"], label=(model.cname+"-train"), color=color, linestyle="dashed")
        plt.plot(hist.epoch, hist.history["val_mse"], label=(model.cname+"-val"), color=color, linestyle="solid")
    plt.title(name+"mse")
    plt.legend()
    plt.savefig(name+"mse.svg")
    plt.close()