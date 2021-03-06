import sys
import os

from models.resnet50 import ResNet50
from models.vgg16 import VGG16
from models.vgg19 import VGG19
from models.inception_v3 import InceptionV3
from models.xception import Xception

from keras.preprocessing.image import ImageDataGenerator
from keras.models import Sequential
from keras.layers import Input, Flatten, Dense, Dropout
from keras.callbacks import ModelCheckpoint, EarlyStopping

import numpy as np
import progressbar
from optparse import OptionParser

sys.setrecursionlimit(40000)
from PIL import ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
parser = OptionParser()

parser.add_option("-p", "--path", dest="train_path", help="Path to training data.")
parser.add_option("-m", "--model", dest="model_name",
				help="Specify a model to train: resnet50, vgg16, vgg19, inception_v3 or xception.")
parser.add_option("-s", "--suffix", dest="suffix",
				help="Model will be saved with provided suffix, i.e. bottleneck_fc_model.[suffix].h5.")
parser.add_option("--num-epochs", dest="num_epochs", help="Number of epochs. Defaults to 50", default=50)
parser.add_option("--batch-size", dest="batch_size",
				help="Batch size. Defaults to 16", default=16)
parser.add_option("--steps-per-epoch", dest="steps_per_epoch",
				help="Steps per epoch. Defaults to 500", default=500)
parser.add_option("--validation-split", dest="validation_split",
				help="Amount of data for validation set. Defaults to 0.15", default=0.15)
parser.add_option("--ignore-saved-features",
                  action="store_true", dest="ignore_saved_features", default=False,
                  help="Ignore saved features for this model and prefix")
parser.add_option("--target-size", dest="target_size",
				help="Target size to resize images to. Defaults to 277", default=277)
parser.add_option("--no-energy-layer",
                  action="store_false", dest="energy_layer", default=True,
                  help="Don't store global average pooling layer at the top of conv layers")
parser.add_option("--optimizer", dest="optimizer",
				help="Optimizer to train the model. Supported values: adam, nadam, adagrad, adadelta, adamax. Defaults to adam. See keras.io/optimizers for more details.", default='adam')

parser.add_option("--rotation-range", dest="rotation_range",
				help="Rotation range for training data. Defaults to 0", default=0.)
parser.add_option("--width-shift-range", dest="width_shift_range",
				help="Width shift range for training data. Defaults to 0", default=0.)
parser.add_option("--height-shift-range", dest="height_shift_range",
				help="Height shift range for training data. Defaults to 0", default=0.)
parser.add_option("--shear-range", dest="shear_range",
				help="Shear range for training data. Defaults to 0", default=0.)
parser.add_option("--zoom-range", dest="zoom_range",
				help="Zoom range for training data. Defaults to 0", default=0.)
parser.add_option("--channel-shift-range", dest="channel_shift_range",
				help="Channel shift range for training data. Defaults to 0", default=0.)
parser.add_option("--fill-mode", dest="fill_mode",
				help="One of constant, nearest, reflect or wrap. Points outside the boundaries of the input are filled according to the given mode. Defaults to nearest",
				default="nearest")
parser.add_option("--cval", dest="cval",
				help="Float or Int. Value used for points outside the boundaries when fill_mode = constant. Defaults to 0", default=0.)
parser.add_option("--horizontal-flip", dest="horizontal_flip",
				action="store_true",
				help="Randomly flip inputs horizontally", default=False)
parser.add_option("--vertical-flip", dest="vertical_flip",
				action="store_true",
				help="Randomly flip inputs vertically", default=False)

(options, args) = parser.parse_args()

rotation_range = float(options.rotation_range)
width_shift_range = float(options.width_shift_range)
height_shift_range = float(options.height_shift_range)
shear_range = float(options.shear_range)
zoom_range = float(options.zoom_range)
channel_shift_range = float(options.channel_shift_range)
fill_mode = options.fill_mode
cval = float(options.cval)
horizontal_flip = options.horizontal_flip
vertical_flip = options.vertical_flip

if options.optimizer not in ('adam', 'nadam', 'adagrad', 'adadelta', 'adamax'):
	parser.error('Error: Supported values for the optimizer: adam, nadam, adagrad, adadelta, adamax. Given {0}'.format(options.optimizer))

if not options.train_path:   # if train path is not given
	parser.error('Error: path to training data must be specified. Pass --path to command line')
data_dir = options.train_path

if not options.model_name:   # if model name is not given
	parser.error('Error: model name must be specified. Pass --model to command line')
model_name = options.model_name

if not options.suffix:   # if suffix is not given
	parser.error('Error: suffix must be specified. Pass --suffix to command line')
suffix = options.suffix

def ensure_dir(file_path):
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

if model_name not in ['resnet50', 'vgg16', 'vgg19', 'inception_v3', 'xception']:
    print("Please choose one of the following")
    print("resnet50, vgg16, vgg19, inception_v3, xception")
    raise ValueError("Model name is invalid")

model_choice = dict(resnet50=ResNet50,
                    vgg16=VGG16,
                    vgg19=VGG19,
                    inception_v3=InceptionV3,
                    xception=Xception)

target_size = int(options.target_size)
num_epochs = int(options.num_epochs)
steps_per_epoch = int(options.steps_per_epoch)
batch_size = int(options.batch_size)

parent_dir = 'fine_tuned_models/' + model_name + '/'
ensure_dir(parent_dir)
features_file = parent_dir + 'train_features.'+suffix+'.npy'
labels_file = parent_dir + 'train_labels.'+suffix+'.npy'
weights_file = parent_dir + 'bottleneck_fc_model.'+suffix+'.h5'

class_names = sorted(os.listdir(data_dir))
np.save(open(parent_dir + 'class_names.'+suffix+'.npy', 'w'), class_names)
num_classes = len(class_names)

def get_train_data():
    if os.path.isfile(features_file) and os.path.isfile(labels_file) and not options.ignore_saved_features:
        train_features = np.load(open(features_file))
        train_labels = np.load(open(labels_file))
        return train_features, train_labels

    train_datagen = ImageDataGenerator(
		rotation_range=rotation_range,
	    width_shift_range=width_shift_range,
	    height_shift_range=height_shift_range,
	    shear_range=shear_range,
	    zoom_range=zoom_range,
	    channel_shift_range=channel_shift_range,
	    fill_mode=fill_mode,
	    cval=cval,
	    horizontal_flip=horizontal_flip,
	    vertical_flip=vertical_flip,
        rescale=1./255)

    train_generator = train_datagen.flow_from_directory(
            data_dir,
            target_size=(target_size, target_size),
            batch_size=batch_size)

    if options.energy_layer:
		model = model_choice[model_name](
	        include_top=False,
	        weights='imagenet',
	        input_shape=(target_size, target_size, 3),
	        pooling='avg')
    else:
		model = model_choice[model_name](
	        include_top=False,
	        weights='imagenet',
	        input_shape=(target_size, target_size, 3))

    print("Extracting features to train on")
    with progressbar.ProgressBar(max_value=steps_per_epoch) as bar:
        i = 0
        for batch, labels in train_generator:
            predictions = model.predict_on_batch(batch)
            if i == 0:
                train_features = predictions
                train_labels = labels
            else:
                train_features = np.concatenate([train_features, predictions])
                train_labels = np.concatenate([train_labels, labels])
            i += 1
            bar.update(i)
            if i == steps_per_epoch:
                break

    np.save(open(features_file, 'w'), train_features)
    np.save(open(labels_file, 'w'), train_labels)

    return train_features, train_labels

train_data, train_labels = get_train_data()

model = Sequential()
if not options.energy_layer:
	model.add(Flatten(input_shape=train_data.shape[1:]))

if model_name in ['vgg16', 'vgg19', 'resnet50']:
	if options.energy_layer:
		model.add(Dense(4096, activation='relu', input_shape=train_data.shape[1:]))
		model.add(Dense(4096, activation='relu'))
		model.add(Dense(num_classes, activation='softmax'))
	else:
		model.add(Dense(4096, activation='relu'))
		model.add(Dense(4096, activation='relu'))
		model.add(Dense(num_classes, activation='softmax'))
else:
    if options.energy_layer:
        model.add(Dense(num_classes, activation='softmax', input_shape=train_data.shape[1:]))
    else:
        model.add(Dense(num_classes, activation='softmax'))

model.compile(
    loss='categorical_crossentropy',
    optimizer=options.optimizer,
    metrics=['accuracy'])

print("Start training")
model.fit(train_data, train_labels,
    epochs=num_epochs,
    batch_size=batch_size,
    validation_split=float(options.validation_split),
    callbacks=[
        ModelCheckpoint(weights_file, save_best_only=True, verbose=2, monitor="val_acc")
    ])
