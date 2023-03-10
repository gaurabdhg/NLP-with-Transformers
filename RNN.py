import os

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

class Vocabulary:

    def __init__(self, pad_token="<pad>", unk_token='<unk>'):
        self.id_to_string = {}
        self.string_to_id = {}
        
        # add the default pad token
        self.id_to_string[0] = pad_token
        self.string_to_id[pad_token] = 0
        
        # add the default unknown token
        self.id_to_string[1] = unk_token
        self.string_to_id[unk_token] = 1        
        
        # shortcut access
        self.pad_id = 0
        self.unk_id = 1
        
    def __len__(self):
        return len(self.id_to_string)

    def add_new_word(self, string):
        self.string_to_id[string] = len(self.string_to_id)
        self.id_to_string[len(self.id_to_string)] = string

    # Given a string, return ID
    def get_idx(self, string, extend_vocab=False):
        if string in self.string_to_id:
            return self.string_to_id[string]
        elif extend_vocab:  # add the new word
            self.add_new_word(string)
            return self.string_to_id[string]
        else:
            return self.unk_id


# Read the raw txt file and generate a 1D PyTorch tensor
# containing the whole text mapped to sequence of token IDs, and a vocab object.
class TextData:

    def __init__(self, file_path, vocab=None, extend_vocab=True, device='cuda'):
        self.data, self.vocab = self.text_to_data(file_path, vocab, extend_vocab, device)
        
    def __len__(self):
            return len(self.data)

    def text_to_data(self, text_file, vocab, extend_vocab, device):
        """Read a raw text file and create its tensor and the vocab.

        Args:
          text_file: a path to a raw text file.
          vocab: a Vocab object
          extend_vocab: bool, if True extend the vocab
          device: device

        Returns:
          Tensor representing the input text, vocab file

        """
        assert os.path.exists(text_file)
        if vocab is None:
            vocab = Vocabulary()
        
        data_list = []
        # Construct data
        full_text = []
        print(f"Reading text file from: {text_file}")
        with open(text_file, 'r') as text:
            for line in text:
                
                tokens = list(line)
                for token in tokens:
                    # get index will extend the vocab if the input
                    # token is not yet part of the text.
                    full_text.append(vocab.get_idx(token, extend_vocab=extend_vocab))

        # convert to tensor
        data = torch.tensor(full_text, device=device, dtype=torch.int64)
        
        print("Done.")

        return data, vocab
    

# Since there is no need for schuffling the data, we just have to split
# the text data according to the batch size and bptt length.
# The input to be fed to the model will be batch[:-1]
# The target to be used for the loss will be batch[1:]
class DataBatches:

    def __init__(self, data, bsz, bptt_len, pad_id):
        self.batches = self.create_batch(data, bsz, bptt_len, pad_id)

    def __len__(self):
        return len(self.batches)

    def __getitem__(self, idx):
        return self.batches[idx]

    def create_batch(self, input_data, bsz, bptt_len, pad_id):
        """Create batches from a TextData object .

        Args:
          input_data: a TextData object.
          bsz: int, batch size
          bptt_len: int, bptt length
          pad_id: int, ID of the padding token

        Returns:
          List of tensors representing batches

        """
        batches = []  # each element in `batches` is (len, B) tensor
        text_len = len(input_data)
        segment_len = text_len // bsz + 1

        # Question: Explain the next two lines!
        padded = input_data.data.new_full((segment_len * bsz,), pad_id)
        
        padded[:text_len] = input_data.data
        padded = padded.view(bsz, segment_len).t()
        num_batches = segment_len // bptt_len + 1
        
        for i in range(num_batches):
            # Prepare batches such that the last symbol of the current batch
            # is the first symbol of the next batch.
            if i == 0:
                # Append a dummy start symbol using pad token
                batch = torch.cat(
                    [padded.new_full((1, bsz), pad_id),
                     padded[i * bptt_len:(i + 1) * bptt_len]], dim=0)
                batches.append(batch)
            else:
                batches.append(padded[i * bptt_len - 1:(i + 1) * bptt_len])
        
        return batches

# downlaod the text

!wget http://www.gutenberg.org/files/49010/49010-0.txt

text_path = "/content/49010-0.txt"

DEVICE = 'cuda'

batch_size = 32
bptt_len = 64

my_data = TextData(text_path, device=DEVICE)
batches = DataBatches(my_data, batch_size, bptt_len, pad_id=0)

"""## Model"""

# LSTM based language model
class LSTMModel(nn.Module):

    def __init__(self, num_classes, emb_dim, hidden_dim, num_layers):
        """Parameters:
        
          num_classes (int): number of input/output classes
          emb_dim (int): token embedding size
          hidden_dim (int): hidden layer size of RNNs
          num_layers (int): number of RNN layers
        """
        super().__init__()
        self.num_classes = num_classes
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.input_layer = nn.Embedding(num_classes, emb_dim)
        self.lstm = nn.LSTM(emb_dim, hidden_dim, num_layers)
        self.out_layer = nn.Linear(hidden_dim, num_classes)

    def forward(self, input, state):
        emb = self.input_layer(input)
        output, state = self.lstm(emb, state)
        output = self.out_layer(output)
        output = output.view(-1, self.num_classes)
        return output, state

    def init_hidden(self, bsz):
        weight = next(self.parameters())
        return (weight.new_zeros(self.num_layers, bsz, self.hidden_dim),weight.new_zeros(self.num_layers, bsz, self.hidden_dim))


# modified for LSTM...
def custom_detach(h,c):
    return (h.detach(),c.detach())

"""## Decoding"""

@torch.no_grad()
def complete(model, prompt, steps, sample=False):
    """Complete the prompt for as long as given steps using the model.
    
    Parameters:
      model: language model
      prompt (str): text segment to be completed
      steps (int): number of decoding steps.
      sample (bool): If True, sample from the model. Otherwise greedy.

    Returns:
      completed text (str)
    """
    model.eval()
    out_list = []
    
    # forward the prompt, compute prompt's ppl
    prompt_list = []
    char_prompt = list(prompt)
    for char in char_prompt:
        prompt_list.append(my_data.vocab.string_to_id[char])
    x = torch.tensor(prompt_list).to(DEVICE).unsqueeze(1)
    
    (state_h,state_c) = model.init_hidden(1)
    logits, (state_h,state_c) = model(x, (state_h,state_c))
    probs = F.softmax(logits[-1], dim=-1)
        
    if sample:
       ix=torch.multinomial(probs, num_samples=1)
    else:
        max_p, ix = torch.topk(probs, k=1, dim=-1)

    out_list.append(my_data.vocab.id_to_string[int(ix)])
    x = ix.unsqueeze(1)
    
    # decode 
    for k in range(steps):
        logits, (state_h,state_c) = model(x, (state_h,state_c))
        probs = F.softmax(logits, dim=-1)
        if sample:  # sample from the distribution or take the most likely
            ix=torch.multinomial(probs, num_samples=1).item()
        else:
            _, ix = torch.topk(probs, k=1, dim=-1)
        out_list.append(my_data.vocab.id_to_string[int(ix)])
        x = ix
    return ''.join(out_list)

learning_rate = 0.001
clipping = 1.0
embedding_size = 64
rnn_size = 2048
rnn_num_layers = 1

# vocab_size = len(module.vocab.itos)
vocab_size = len(my_data.vocab.id_to_string)
print(F"vocab size: {vocab_size}")

model = LSTMModel(
    num_classes=vocab_size, emb_dim=embedding_size, hidden_dim=rnn_size,
    num_layers=rnn_num_layers)
model = model.to(DEVICE)
hidden = model.init_hidden(batch_size)

loss_fn = nn.CrossEntropyLoss(ignore_index=0)
optimizer = torch.optim.Adam(params=model.parameters(), lr=learning_rate)

"""## Training loop"""

# Training

num_epochs = 30
report_every = 30
prompt = "Dogs like best to"
pplxty=list([])

for ep in range(num_epochs):
    print(f"=== start epoch {ep} ===")
    state_h,state_c = model.init_hidden(batch_size)
    for idx in range(len(batches)):
        batch = batches[idx]
        model.train()
        optimizer.zero_grad()
        state_h,state_c = custom_detach(state_h,state_c)
        
        input = batch[:-1]
        target = batch[1:].reshape(-1)

        bsz = input.shape[1]
        prev_bsz = state_h.shape[1]
        if bsz != prev_bsz:
            state = state[:, :bsz, :]
        output, (state_h,state_c) = model(input, (state_h,state_c))
        pplx=torch.exp(loss_fn(output,target))
        pplxty.append(pplx.item())
        pplx.backward()
        #loss = loss_fn(output, target)
        #loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), clipping)
        optimizer.step()
        if idx % report_every == 0:
            #print(f"train loss: {loss.item()}")  # replace me by the line below!
            print(f"train ppl: {pplx.item()}")
            generated_text = complete(model, prompt, 128, sample=True)
            print(f'----------------- epoch/batch {ep}/{idx} -----------------')
            print(prompt)
            print(generated_text)
            print(f'----------------- end generated text -------------------')

complete(model, "THE DONKEY IN THE SHEEP SKIN", 512, sample=False)


#plotting the evolution of pplxty.
import numpy as np
import matplotlib.pyplot as plt

xdata=np.arange(len(pplxty))
fig=plt.plot(xdata,pplxty)
plt.savefig('pplxty.jpg',dpi=512)

#pplxty evolution for LSTM
fig=plt.plot(xdata,pplxty)
plt.axhline(y=1.03,color='r',linewidth=0.5)
plt.savefig('pplxty103.jpg',dpi=512)

complete(model, "THE TWO FROGS", 512, sample=False)

complete(model, "THE GIRL DANCING", 800, sample=False)#SIMILAR TO:: THE BOY BATHING

complete(model, "THE SNAKE AND THE FARMER", 512, sample=False)

complete(model, "THE FOOLISH BOY", 1024, sample=False)
