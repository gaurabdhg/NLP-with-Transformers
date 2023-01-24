import os
import math
import time
from tqdm import tqdm

import torch
import torch.nn as nn
from torch.utils.data import Dataset
from torch.utils.data import DataLoader

from google.colab import drive
drive.mount('/DLL')

class Vocabulary:

    def __init__(self, pad_token="<pad>", unk_token='<unk>', eos_token='<eos>', sos_token='<sos>'):
        self.id_to_string = {}
        self.string_to_id = {}
        
        # add the default pad token
        self.id_to_string[0] = pad_token
        self.string_to_id[pad_token] = 0
        
        # add the default unknown token
        self.id_to_string[1] = unk_token
        self.string_to_id[unk_token] = 1
        
        # add the default unknown token
        self.id_to_string[2] = eos_token
        self.string_to_id[eos_token] = 2   

        # add the default unknown token
        self.id_to_string[3] = sos_token
        self.string_to_id[sos_token] = 3

        # shortcut access
        self.pad_id = 0
        self.unk_id = 1
        self.eos_id = 2
        self.sos_id = 3

    def __len__(self):
        return len(self.id_to_string)

    def add_new_word(self, string):
        self.string_to_id[string] = len(self.string_to_id)
        self.id_to_string[len(self.id_to_string)] = string

    # Given a string, return ID
    # if extend_vocab is True, add the new word
    def get_idx(self, string, extend_vocab=False):
        if string in self.string_to_id:
            return self.string_to_id[string]
        elif extend_vocab:  # add the new word
            self.add_new_word(string)
            return self.string_to_id[string]
        else:
            return self.unk_id


# Read the raw txt file and generate a 1D pytorch tensor
# containing the whole text mapped to sequence of token ID,
# and a vocab file
class ParallelTextDataset(Dataset):

    def __init__(self, src_file_path, trg_file_path, src_vocab=None,
                 trg_vocab=None, extend_vocab=False, device='cuda'):
        (self.data, self.src_vocab, self.trg_vocab,
         self.src_max_seq_length, self.tgt_max_seq_length) = self.parallel_text_to_data(
            src_file_path, trg_file_path, src_vocab, trg_vocab, extend_vocab, device)

    def __getitem__(self, idx):
        return self.data[idx]

    def __len__(self):
        return len(self.data)

    def parallel_text_to_data(self, src_file, tgt_file, src_vocab=None, tgt_vocab=None,
                          extend_vocab=False, device='cuda'):
        # Convert paired src/tgt texts into torch.tensor data.
        # All sequences are padded to the length of the longest sequence
        # of the respective file.

        assert os.path.exists(src_file)
        assert os.path.exists(tgt_file)

        if src_vocab is None:
            src_vocab = Vocabulary()

        if tgt_vocab is None:
            tgt_vocab = Vocabulary()
        
        data_list = []
        # Check the max length, if needed construct vocab file.
        src_max = 0
        with open(src_file, 'r') as text:
            for line in text:
                tokens = list(line)
                length = len(tokens)
                if src_max < length:
                    src_max = length

        tgt_max = 0
        with open(tgt_file, 'r') as text:
            for line in text:
                tokens = list(line)
                length = len(tokens)
                if tgt_max < length:
                    tgt_max = length
        tgt_max += 2  # add for begin/end tokens
                    
        src_pad_idx = src_vocab.pad_id
        tgt_pad_idx = tgt_vocab.pad_id

        tgt_eos_idx = tgt_vocab.eos_id
        tgt_sos_idx = tgt_vocab.sos_id

        # Construct data
        src_list = []
        print(f"Loading source file from: {src_file}")
        with open(src_file, 'r') as text:
            for line in tqdm(text):
                seq = []
                tokens = list(line)
                for token in tokens:
                    seq.append(src_vocab.get_idx(token, extend_vocab=extend_vocab))
                var_len = len(seq)
                var_seq = torch.tensor(seq, device=device, dtype=torch.int64)
                # padding
                new_seq = var_seq.data.new(src_max).fill_(src_pad_idx)
                new_seq[:var_len] = var_seq
                src_list.append(new_seq)

        tgt_list = []
        print(f"Loading target file from: {tgt_file}")
        with open(tgt_file, 'r') as text:
            for line in tqdm(text):
                seq = []
                tokens = list(line)
                # append a start token
                seq.append(tgt_sos_idx)
                for token in tokens:
                    seq.append(tgt_vocab.get_idx(token, extend_vocab=extend_vocab))
                # append an end token
                seq.append(tgt_eos_idx)

                var_len = len(seq)
                var_seq = torch.tensor(seq, device=device, dtype=torch.int64)

                # padding
                new_seq = var_seq.data.new(tgt_max).fill_(tgt_pad_idx)
                new_seq[:var_len] = var_seq
                tgt_list.append(new_seq)

        # src_file and tgt_file are assumed to be aligned.
        assert len(src_list) == len(tgt_list)
        for i in range(len(src_list)):
            data_list.append((src_list[i], tgt_list[i]))

        print("Done.")
            
        return data_list, src_vocab, tgt_vocab, src_max, tgt_max

# `DATASET_DIR` should be modified to the directory where you downloaded the dataset.
DATASET_DIR = "/DLL/MyDrive/DLL"

TRAIN_FILE_NAME = "train"
VALID_FILE_NAME = "interpolate"

INPUTS_FILE_ENDING = ".x"
TARGETS_FILE_ENDING = ".y"

TASK = "numbers__place_value"
# TASK = "comparison__sort"
# TASK = "algebra__linear_1d"

# Adapt the paths!

src_file_path = f"{DATASET_DIR}/{TASK}/{TRAIN_FILE_NAME}{INPUTS_FILE_ENDING}"
trg_file_path = f"{DATASET_DIR}/{TASK}/{TRAIN_FILE_NAME}{TARGETS_FILE_ENDING}"

train_set = ParallelTextDataset(src_file_path, trg_file_path, extend_vocab=True)

# get the vocab
src_vocab = train_set.src_vocab
trg_vocab = train_set.trg_vocab

src_file_path = f"{DATASET_DIR}/{TASK}/{VALID_FILE_NAME}{INPUTS_FILE_ENDING}"
trg_file_path = f"{DATASET_DIR}/{TASK}/{VALID_FILE_NAME}{TARGETS_FILE_ENDING}"

valid_set = ParallelTextDataset(
    src_file_path, trg_file_path, src_vocab=src_vocab, trg_vocab=trg_vocab,
    extend_vocab=False)

batch_size = 64

train_data_loader = DataLoader(
    dataset=train_set, batch_size=batch_size, shuffle=True)

valid_data_loader = DataLoader(
    dataset=valid_set, batch_size=batch_size, shuffle=False)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

src_vocab.id_to_string

trg_vocab.id_to_string

########
# Taken from:
# https://pytorch.org/tutorials/beginner/transformer_tutorial.html
# or also here:c
# https://github.com/pytorch/examples/blob/master/word_language_model/model.py
class PositionalEncoding(nn.Module):

    def __init__(self, d_model, dropout=0.0, max_len=5000):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(p=dropout)
        self.max_len = max_len

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float()
                             * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)  # shape (max_len, 1, dim)
        self.register_buffer('pe', pe)  # Will not be trained.

    def forward(self, x):
        """Inputs of forward function
        Args:
            x: the sequence fed to the positional encoder model (required).
        Shape:
            x: [sequence length, batch size, embed dim]
            output: [sequence length, batch size, embed dim]
        """
        assert x.size(0) < self.max_len, (
            f"Too long sequence length: increase `max_len` of pos encoding")
        # shape of x (len, B, dim)
        x = x + self.pe[:x.size(0), :]
        return self.dropout(x)

class TransformerModel(nn.Module):
    def __init__(self, source_vocabulary_size, target_vocabulary_size,
                 d_model=256, pad_id=0, encoder_layers=3, decoder_layers=2,
                 dim_feedforward=1024, num_heads=8):
        # all arguments are (int)
        super().__init__()
        self.pad_id = pad_id

        self.embedding_src = nn.Embedding(
            source_vocabulary_size, d_model, padding_idx=pad_id)
        self.embedding_tgt = nn.Embedding(
            target_vocabulary_size, d_model, padding_idx=pad_id)

        self.pos_encoder = PositionalEncoding(d_model)
        self.transformer = nn.Transformer(
            d_model, num_heads, encoder_layers, decoder_layers, dim_feedforward)
        self.encoder = self.transformer.encoder
        self.decoder = self.transformer.decoder
        self.linear = nn.Linear(d_model, target_vocabulary_size)

    def create_src_padding_mask(self,src):
        # input src of shape ()
        src_padding_mask = src.transpose(0, 1) == 0
        return src_padding_mask

    def create_tgt_padding_mask(self,tgt):
        # input tgt of shape ()
        tgt_padding_mask = tgt.transpose(0, 1) == 0
        return tgt_padding_mask


    def forward(self, src, tgt):
        """Forward function.

        Parameters:
          src: tensor of shape (sequence_length, batch, data dim)
          tgt: tensor of shape (sequence_length, batch, data dim)
        Returns:
          tensor of shape (sequence_length, batch, data dim)
        """
        
        src_key_padding_mask = self.create_src_padding_mask(src).to(DEVICE)
        tgt_key_padding_mask = self.create_tgt_padding_mask(tgt).to(DEVICE)
        memory_key_padding_mask = src_key_padding_mask
        tgt_mask = nn.Transformer.generate_square_subsequent_mask(
            tgt.shape[0]).to(DEVICE)

        tgt = self.embedding_tgt(tgt)
        tgt = self.pos_encoder(tgt)
        out = self.embedding_src(src)
        out = self.pos_encoder(out)
        out = self.transformer(
            out, tgt, src_key_padding_mask=src_key_padding_mask,
            tgt_mask=tgt_mask, tgt_key_padding_mask=tgt_key_padding_mask,
            memory_key_padding_mask=memory_key_padding_mask)
        
        out = self.linear(out)
        return out

    def forward_separate(self,src,tgt):
        src_key_padding_mask = self.create_src_padding_mask(src).to(DEVICE)
        tgt_key_padding_mask = self.create_tgt_padding_mask(tgt).to(DEVICE)
        memory_key_padding_mask = src_key_padding_mask
        tgt_mask = nn.Transformer.generate_square_subsequent_mask(
            tgt.shape[0]).to(DEVICE)

        tgt = self.embedding_tgt(tgt)
        tgt = self.pos_encoder(tgt)
        out = self.embedding_src(src)
        out = self.pos_encoder(out)

        # Encode the source sequence
        encoder_output = self.encoder(src,src_key_padding_mask=src_key_padding_mask)

        # Decode the target sequence
        decoder_output = self.decoder(tgt, encoder_output,
                                      tgt_mask=tgt_mask, tgt_key_padding_mask=tgt_key_padding_mask,
                                  memory_key_padding_mask=memory_key_padding_mask)

        out = self.linear(decoder_output)

        return out

        
    def greedy_search(self, src, tgt, max_len=100, start_token=3, eos_token=2):
        self.eval()
        with torch.no_grad():
            src_padding_mask = self.create_src_padding_mask(src)
            tgt_padding_mask = self.create_tgt_padding_mask(tgt)
            memory_key_padding_mask=src_padding_mask
            tgt_mask=nn.Transformer.generate_square_subsequent_mask(tgt.shape[0]).to(DEVICE)

            tgt=self.embedding_tgt(tgt)
            tgt=self.pos_encoder(tgt)
            out=self.embedding_src(src)
            out=self.pos_encoder(out)

            enc_output = self.encoder(src)

            dec_input = torch.LongTensor([[start_token]] * src.shape[1]).to(DEVICE)

            pred = []

            for i in range(max_len):
                dec_output = self.decoder(dec_input, enc_output, tgt_padding_mask)
                pred_tokens = dec_output.argmax(dim=-1)

                current = [pred[j] + [pred_tokens[j].item()] for j in range(src.shape[1])]
                
                stop_criteria = [pred_tokens[j] == eos_token or dec_input.shape[1] > tgt.shape[1] for j in range(src.shape[1])]
                
                if all(stop_criteria):
                    break
                else:
                    dec_input = torch.cat((dec_input, pred_tokens), dim=1)

                pred = current

            return pred

def compute_accuracy(preds, tgt_):
    correct = 0
    total = tgt_.shape[0]
    for i in range(total):
        #print(preds[i],tgt[i])
        if (preds[i] == tgt_[i]).all:
            correct += 1
    return correct/total

# Hyperparameters
num_epochs = 3
learning_rate = 1e-5
accumulation_steps = 100  # No. of steps to accumulate gradients before updating parameters

pad_id=0
source_vocab_size=len(src_vocab.id_to_string)
target_vocab_size=len(trg_vocab.id_to_string)
max_len=100

n=5000

model = TransformerModel(source_vocab_size, target_vocab_size)

loss_fn = nn.CrossEntropyLoss(ignore_index=pad_id)
optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

model.to(DEVICE)
loss_fn.to(DEVICE)

tloss=[]
tacc=[]
vloss=[]
vacc=[]

# Training loop
for epoch in range(num_epochs):
    train_loss = 0
    valid_loss=0
    train_acc=0
    val_acc=0
    
    model.train()
    for i, (src, tgt) in enumerate(train_data_loader):
        src, tgt = src.to(DEVICE), tgt.to(DEVICE)
    
        optimizer.zero_grad()
        
        #torch.autograd.set_detect_anomaly(True)
        
        output = model(src.transpose(0,1),tgt.transpose(0,1))
        #output = model.forward_separate(src.permute(1,0),tgt)
        output = output.permute(1,2,0)
        #print(output)
        
        loss = loss_fn(output, tgt)
        train_loss+=loss.item()
        
        loss.backward()

        torch.nn.utils.clip_grad_norm_(model.parameters(), 0.1)

        # Accumulate gradients
        if (i + 1) % accumulation_steps == 0:
            optimizer.step()

        if i % n == 0 :
            train_acc = compute_accuracy(output, tgt)
            print(f"Epoch: [{epoch+1}/{num_epochs}], Step: [{i+1}/{len(train_data_loader)}], Loss: {train_loss/n:.4f}, Accuracy: {train_acc:.4f}")
            tloss.append(train_loss)
            tacc.append(train_acc)
            train_loss=0
            train_acc=0
        #if i>1000:break
            
    model.eval()
    with torch.no_grad():
      for i, (valsrc, valtgt) in enumerate(valid_data_loader):
          
          valsrc, valtgt = src.to(DEVICE), tgt.to(DEVICE)
          
          output = model(valsrc.transpose(0,1),valtgt.transpose(0,1))
          
          output = output.permute(1,2,0)
          
          loss = loss_fn(output, tgt) 
          valid_loss+=loss.detach().item()  
          val_acc += compute_accuracy(output, valtgt)
      print(f"Epoch: [{epoch+1}], Step: [Validation], Loss: {valid_loss/i:.4f}, Accuracy: {val_acc/i:.4f}")
      vloss.append(valid_loss)
      vacc.append(val_acc)

print(f"Epoch: [{epoch+1}], Step: [Validation], Loss: {valid_loss:.4f}")

import matplotlib.pyplot as plt

# tacc and tloss are lists that contain the training accuracy and loss at each iteration

plt.plot(range(len(tacc)), tacc,'r', label='Training accuracy')

plt.plot(range(len(tloss)), tloss,'b', label='Training loss')

plt.legend()
plt.xlabel('Iteration')
plt.ylabel('Accuracy/Loss')

plt.savefig('train.png',dpi=360)
plt.show()

plt.plot(range(len(vacc)), vacc,'r', label='Valid accuracy')

plt.plot(range(len(vloss)), vloss,'b', label='Valid loss')

plt.legend()
plt.xlabel('Iteration')
plt.ylabel('Accuracy/Loss')

plt.savefig('train.png',dpi=360)
plt.show()
