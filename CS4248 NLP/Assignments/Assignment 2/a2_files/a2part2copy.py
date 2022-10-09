import os
import re
import sys
import string
import argparse
import datetime
import itertools
from unidecode import unidecode

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

torch.manual_seed(0)


class LangDataset(Dataset):
    """
    Define a pytorch dataset class that accepts a text path, and optionally label path and
    a vocabulary (depends on your implementation). This class holds all the data and implement
    a __getitem__ method to be used by a Python generator object or other classes that need it.

    DO NOT shuffle the dataset here, and DO NOT pad the tensor here.
    """
    def __init__(self, text_path, label_path=None, vocab=None):
        """
        Read the content of vocab and text_file
        Args:
            vocab (string): Path to the vocabulary file.
            text_file (string): Path to the text file.
        """
        raw_texts = self.file_to_list(text_path)
        self.texts = self.preprocess(raw_texts)
        self.labels = self.file_to_list(label_path)

        # Training phase
        if vocab is None:
            self.text_vocab = self.create_text_vocab(self.texts) # 661
            self.label_vocab = self.create_label_vocab(self.labels) # 5
        else:
            # Testing phase
            self.text_vocab = vocab['texts']
            self.label_vocab = vocab['labels']

    
    def file_to_list(self, file_path):
        if file_path is None:
            return []

        with open(file_path) as data:
            output = []
            for line in data:
                output.append(line.rstrip())

        return output


    def preprocess(self, raw_data):
        data = []

        for text in raw_data:
            text = re.sub('[^a-z]+',' ', unidecode(text.lower()))
            characters = [c for c in text]
            bigram_list = []

            for i in range(len(characters)-1):
                bigram = characters[i] + characters[i+1]
                bigram_list.append(bigram)

            data.append(bigram_list)

        return data


    def create_text_vocab(self, data):
        text_vocab = {}
        for sent in data:
            for word in sent:
                if word not in text_vocab:
                    text_vocab[word] = len(text_vocab)+1

        text_vocab['unk'] = len(text_vocab)+1
        
        return text_vocab


    def create_label_vocab(self, data):
        label_vocab = {}
        for label in data:
            if label not in label_vocab:
                label_vocab[label] = len(label_vocab)
        
        return label_vocab


    def vocab_size(self):
        """
        A function to inform the vocab size. The function returns two numbers:
            num_vocab: size of the vocabulary
            num_class: number of class labels
        """
        num_vocab = len(self.text_vocab)
        num_class = len(self.label_vocab)
        return num_vocab, num_class
    

    def __len__(self):
        """
        Return the number of instances in the data
        """
        return len(self.texts)


    def __getitem__(self, i):
        """
        Return the i-th instance in the format of:
            (text, label)
        Text and label should be encoded according to the vocab (word_id).

        DO NOT pad the tensor here, do it at the collator function.
        """
        bigrams = self.texts[i]
        text = []
        for bigram in bigrams:
            if bigram in self.text_vocab.keys():
                text.append(self.text_vocab[bigram])
            else:
                text.append(self.text_vocab['unk'])

        if len(self.labels) == 0:
            return text

        label = self.label_vocab[self.labels[i]]
        return text, label


def collator(batch):
    """
    Define a function that receives a list of (text, label) pair
    and return a pair of tensors:
        texts: a tensor that combines all the text in the mini-batch, pad with 0
        labels: a tensor that combines all the labels in the mini-batch
    """
    data = []
    labels = []

    for items in batch:
        if type(items) == list:
            data.append(items)
        else:
            data.append(items[0])
            labels.append(items[1])

    padded_data = zip(*itertools.zip_longest(*data, fillvalue=0))
    texts = torch.tensor(list(padded_data))

    if len(labels) != 0:
        labels = torch.LongTensor(labels)
    else:
        labels = None
    
    return texts, labels


def make_bow_vector(sentence, vocab_size):
    vec = torch.zeros(vocab_size)

    for word in sentence:
        if word == 0: # padding
            break

        if word <= vocab_size:
            vec[word-1] += 1
        else:
            vec[vocab_size-1] += 1 # unknown word

    return vec


class Model(nn.Module):
    """
    Define a model that with one embedding layer with dimension 16 and
    a feed-forward layers that reduce the dimension from 16 to 200 with ReLU activation
    a dropout layer, and a feed-forward layers that reduce the dimension from 200 to num_class
    """
    def __init__(self, num_vocab, num_class, dropout=0.3):
        super().__init__()
        # define your model here
        self.embedding = nn.Linear(num_vocab, 200)
        self.output = nn.Linear(200, num_class)
        self.dropout = nn.Dropout(p=dropout)

    def forward(self, x):
        # define the forward function here
        h1 = self.dropout(self.embedding(x))
        activated_h1 = F.relu(h1)
        output = self.output(activated_h1)

        probs = F.softmax(output, dim=1)

        return probs


def train(model, dataset, batch_size, learning_rate, num_epoch, device='cpu', model_path=None):
    """
    Complete the training procedure below by specifying the loss function
    and optimizers with the specified learning rate and specified number of epoch.
    
    Do not calculate the loss from padding.
    """
    data_loader = DataLoader(dataset, batch_size=batch_size, collate_fn=collator, shuffle=True)

    # assign these variables
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=learning_rate, momentum=0.9)

    start = datetime.datetime.now()
    for epoch in range(num_epoch):
        model.train()
        running_loss = 0.0
        for step, data in enumerate(data_loader, 0):
            # get the inputs; data is a tuple of (inputs, labels)
            texts = data[0].to(device)
            labels = data[1].to(device)

            vocab_size, _ = dataset.vocab_size()
            texts = [make_bow_vector(x, vocab_size) for x in texts]
            texts = torch.stack(texts).to(device)

            # zero the parameter gradients
            optimizer.zero_grad()

            # do forward propagation
            probabilities = model(texts)

            # do loss calculation
            loss = criterion(probabilities, labels)

            # do backward propagation
            loss.backward()

            # do parameter optimization step
            optimizer.step()

            # calculate running loss value for non padding
            running_loss += loss.item()

            # print loss value every 100 steps and reset the running loss
            if step % 100 == 99:
                print('[%d, %5d] loss: %.3f' %
                    (epoch + 1, step + 1, running_loss / 100))
                running_loss = 0.0

    end = datetime.datetime.now()
    
    # define the checkpoint and save it to the model path
    # tip: the checkpoint can contain more than just the model
    checkpoint = {
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'loss': loss.item(),
        'vocabulary': {
            'texts': dataset.text_vocab,
            'labels': dataset.label_vocab
        }
    }
    torch.save(checkpoint, model_path)

    print('Model saved in ', model_path)
    print('Training finished in {} minutes.'.format((end - start).seconds / 60.0))


def test(model, dataset, class_map, device='cpu'):
    model.eval()
    data_loader = DataLoader(dataset, batch_size=20, collate_fn=collator, shuffle=False)

    labels = []
    with torch.no_grad():
        for data in data_loader:
            texts = data[0].to(device)

            vocab_size, _ = dataset.vocab_size()
            texts = [make_bow_vector(x, vocab_size) for x in texts]
            texts = torch.stack(texts).to(device)
            outputs = model(texts).cpu()

            # get the label predictions
            predictions = torch.argmax(outputs, dim=1).tolist()
            for p in predictions:
                labels.append(class_map[p])

    return labels


def main(args):
    if torch.cuda.is_available():
        device_str = 'cuda:{}'.format(0)
    else:
        device_str = 'cpu'
    device = torch.device(device_str)
    
    assert args.train or args.test, "Please specify --train or --test"
    if args.train:
        assert args.label_path is not None, "Please provide the labels for training using --label_path argument"
        dataset = LangDataset(args.text_path, args.label_path)
        num_vocab, num_class = dataset.vocab_size()
        model = Model(num_vocab, num_class).to(device)
        
        # you may change these hyper-parameters
        learning_rate = 0.05
        batch_size = 20
        num_epochs = 20

        train(model, dataset, batch_size, learning_rate, num_epochs, device, args.model_path)
    if args.test:
        assert args.model_path is not None, "Please provide the model to test using --model_path argument"
        
        # create the test dataset object using LangDataset class
        checkpoint = torch.load(args.model_path)
        dataset = LangDataset(args.text_path, label_path=None, vocab=checkpoint['vocabulary'])
        num_vocab, num_class = dataset.vocab_size()

        # initialize and load the model
        model = Model(num_vocab, num_class)
        model.load_state_dict(checkpoint['model_state_dict'])

        # the lang map should contain the mapping between class id to the language id (e.g. eng, fra, etc.)
        label_vocab = checkpoint['vocabulary']['labels']
        lang_map = {v: k for k, v in label_vocab.items()}

        # run the prediction
        preds = test(model, dataset, lang_map, device)
        
        # write the output
        with open(args.output_path, 'w', encoding='utf-8') as out:
            out.write('\n'.join(preds))
    print('\n==== A2 Part 2 Done ====')


def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text_path', help='path to the text file')
    parser.add_argument('--label_path', default=None, help='path to the label file')
    parser.add_argument('--train', default=False, action='store_true', help='train the model')
    parser.add_argument('--test', default=False, action='store_true', help='test the model')
    parser.add_argument('--model_path', required=True, help='path to the output file during testing')
    parser.add_argument('--output_path', default='out.txt', help='path to the output file during testing')
    return parser.parse_args()

if __name__ == "__main__":
    args = get_arguments()
    main(args)