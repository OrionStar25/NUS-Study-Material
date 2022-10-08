import argparse
import datetime
import itertools
from collections import Counter

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
        def __file_to_list(file_path):
            with open(file_path) as data:
                output = []
                for line in data:
                    output.append(line.rstrip())

            return output

        label_dict = {'eng': 0, 'deu': 1, 'fra': 2, 'ita': 3, 'spa': 4}
        self.labels = []
        if label_path is not None:
            labels = __file_to_list(label_path)
            for label in labels:
                self.labels.append(label_dict[label])

        if vocab is not None:
            self.vocab = vocab

        data = __file_to_list(text_path)
        self.texts = []
        if vocab is None:
            self.vocab = {'unk': 1}
            count = 2

        for text in data:
            characters = ['$'] + [c for c in text] + ['$']
            bigram_list = []
            
            for i in range(len(characters)-1):
                bigram = characters[i] + characters[i+1]
                bigram_list.append(bigram)

                if vocab is None and bigram not in self.vocab.keys():
                    self.vocab[bigram] = count
                    count += 1

            self.texts.append(bigram_list)


    def vocab_size(self):
        """
        A function to inform the vocab size. The function returns two numbers:
            num_vocab: size of the vocabulary
            num_class: number of class labels
        """
        num_vocab = len(self.vocab)
        num_class = len(Counter(self.labels))

        if num_class == 0:
            num_class = 5

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
            if bigram in self.vocab.keys():
                text.append(self.vocab[bigram])
            else:
                text.append(self.vocab['unk'])

        if len(self.labels) == 0:
            return text
        
        return text, self.labels[i]


class Model(nn.Module):
    """
    Define a model that with one embedding layer with dimension 16 and
    a feed-forward layers that reduce the dimension from 16 to 200 with ReLU activation
    a dropout layer, and a feed-forward layers that reduce the dimension from 200 to num_class
    """
    def __init__(self, num_vocab, num_class, dropout=0.3):
        super().__init__()
        # define your model here
        self.vocab_size = num_vocab

        self.embedding = nn.Linear(20, 200)
        self.out = nn.Linear(200, num_class)
        self.dropout = nn.Dropout(p=dropout)

    def forward(self, x):
        # define the forward function here
        data = self.__embed_input(x)
        h1 = self.dropout(self.embedding(data))

        activated_h1 = F.relu(h1)
        out = self.out(activated_h1)

        output = F.softmax(out, dim=1)
        return output

    def __embed_input(self, x):
        d = len(x)
        input_data = x.tolist()
        embedding_matrix = [[0 for _ in range(self.vocab_size)] for _ in range(d)]

        for i, bigrams in enumerate(input_data):
            count_of_each_bigram = Counter(bigrams)
            
            for bigram, count in count_of_each_bigram.items():
                if bigram != 0: # If not padding
                    embedding_matrix[i][bigram-1] = count

        compact_embeddings = list(zip(*embedding_matrix))
        data = []
        for bigrams in input_data:
            feature = []
            for bigram in bigrams:
                if bigram == 0: # ignore padding in average
                    break
                
                feature.append(list(compact_embeddings[bigram-1])) # k * d

            compact_feature = list(zip(*feature))
            k = len(feature)
            averaged_feature = []

            for i in range(d):
                average = sum(compact_feature[i]) / k
                averaged_feature.append(average)

            data.append(averaged_feature)

        return torch.tensor(data)


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
        labels = torch.tensor(labels)
    else:
        labels = None

    return texts, labels


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

            # zero the parameter gradients
            optimizer.zero_grad()

            # do forward propagation
            prediction = model.forward(texts)

            # do loss calculation
            loss = criterion(prediction, labels)

            # do backward propagation
            loss.backward()

            # do parameter optimization step
            optimizer.step()

            # calculate running loss value for non padding
            running_loss = loss.item() * texts.size(0)

            # print loss value every 100 steps and reset the running loss
            if step % 10 == 9:
                print('[%d, %5d] loss: %.6f' %
                    (epoch + 1, step + 1, running_loss / 100))
                running_loss = 0.0

    end = datetime.datetime.now()
    
    # define the checkpoint and save it to the model path
    # tip: the checkpoint can contain more than just the model
    checkpoint = {
        'model': model,
        'vocabulary': dataset.vocab
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
            outputs = model(texts).cpu()
            print(outputs[0])

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
        learning_rate = 1
        batch_size = 20
        num_epochs = 20

        train(model, dataset, batch_size, learning_rate, num_epochs, device, args.model_path)
    
    if args.test:
        assert args.model_path is not None, "Please provide the model to test using --model_path argument"
        
        # create the test dataset object using LangDataset class
        checkpoint = torch.load(args.model_path)
        dataset = LangDataset(args.text_path, label_path=None, vocab=checkpoint['vocabulary'])

        # initialize and load the model
        model = checkpoint['model']

        # the lang map should contain the mapping between class id to the language id (e.g. eng, fra, etc.)
        lang_map = {0: 'eng', 1: 'deu', 2: 'fra', 3: 'ita', 4: 'spa'}

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