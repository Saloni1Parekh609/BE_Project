# -*- coding: utf-8 -*-
"""NMT.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/19zVaHYKN0c6A4OKyE1TniCwGSKBzk5Ef
"""

from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import torch
import torch.nn as nn

df = pd.read_csv('/root/BE_Project/dataframe.csv')
df.drop(['Unnamed: 0'], axis = 1, inplace = True)
df.head()

df = df.iloc[:10000,:]
df.shape

df_train, df_val, df_test = np.split(df.sample(frac=1, random_state=42), [int(.9*len(df)), int(.95*len(df))])
print(df_train.shape)
print(df_val.shape)
print(df_test.shape)

words_cypher = []
words_english = []

for i in range(df.shape[0]):
  words_cypher.append(len(df.iloc[i,1].split()))
  words_english.append(len(df.iloc[i,0].split()))

print("Max in cypher: ", max(words_cypher))
print("Max in english: ", max(words_english))

from tokenizers import Tokenizer

cypher_tokenizer = Tokenizer.from_file("/content/drive/MyDrive/BE Project/Datasets/tokenizer_cypher.json")

encoded = cypher_tokenizer.encode('MATCH (var1) WHERE var1.name="Spoon Street"  WITH 1 AS foo, var1.cleanliness AS var2 RETURN var2 [UNK]>')
cypher_tokenizer.decode(encoded.ids)

cypher_tokenizer.enable_padding(pad_id=3, length=128)
cypher_tokenizer.enable_truncation(max_length=128)

english_tokenizer = Tokenizer.from_file("/content/drive/MyDrive/BE Project/Datasets/tokenizer_english.json")

encoded = english_tokenizer.encode('[BOS]' + df.iloc[0, 0] + '[EOS]')
english_tokenizer.decode(encoded.ids)

english_tokenizer.enable_padding(pad_id=3, length=128)
english_tokenizer.enable_truncation(max_length=128)

cypher_tokenizer.get_vocab_size()

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

class NMTDataset(Dataset):
  def __init__(self, dataframe, english_tokenizer, cypher_tokenizer):
    self.dataframe = dataframe
    self.english_tokenizer = english_tokenizer
    self.cypher_tokenizer = cypher_tokenizer

  def __len__(self):
    return len(self.dataframe)

  def generate_square_subsequent_mask(self, sz):
    mask = (torch.triu(torch.ones((sz, sz))) == 1).transpose(0, 1)
    mask = mask.float().masked_fill(mask == 0, float('-inf')).masked_fill(mask == 1, float(0.0))
    return mask.to(device)

  def __getitem__(self, idx):
    self.src = self.dataframe.iloc[idx, 0]
    self.tgt = self.dataframe.iloc[idx, 1]

    self.encoded_eng = self.english_tokenizer.encode('[BOS]' + self.src + '[EOS]')
      
    self.encoded_cyp = self.cypher_tokenizer.encode('[BOS]' + self.tgt + '[EOS]')

    return torch.squeeze(torch.Tensor(self.encoded_eng.ids)).to(device), torch.squeeze(torch.Tensor(self.encoded_eng.attention_mask)).to(device), torch.squeeze(torch.Tensor(self.encoded_cyp.ids)).to(device), torch.squeeze(torch.Tensor(self.encoded_cyp.attention_mask)).to(device) #, self.mask_cyp

train_dataset = NMTDataset(df_train, english_tokenizer, cypher_tokenizer)
trainLoader = torch.utils.data.DataLoader(train_dataset, batch_size=8)

val_dataset = NMTDataset(df_val, english_tokenizer, cypher_tokenizer)
valLoader = torch.utils.data.DataLoader(val_dataset, batch_size=8)

test_dataset = NMTDataset(df_test, english_tokenizer, cypher_tokenizer)
testLoader = torch.utils.data.DataLoader(test_dataset, batch_size=8)

x = NMTDataset(df, english_tokenizer, cypher_tokenizer)
trainLoader=torch.utils.data.DataLoader(x, batch_size=8)

train_iter = iter(trainLoader)
a, b, c, d = train_iter.next()

print(a.shape)
print(b.shape)
print(c.shape)
print(d.shape)

from torch.autograd import Variable
import math

class PositionalEncoder(nn.Module):
    def __init__(self, d_model, max_seq_len = 80):
        super().__init__()
        self.d_model = d_model
        
        # create constant 'pe' matrix with values dependant on 
        # pos and i
        pe = torch.zeros(max_seq_len, d_model)
        for pos in range(max_seq_len):
            for i in range(0, d_model, 2):
                pe[pos, i] = \
                math.sin(pos / (10000 ** ((2 * i)/d_model)))
                pe[pos, i + 1] = \
                math.cos(pos / (10000 ** ((2 * (i + 1))/d_model)))
                
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)
 
    
    def forward(self, x):
        # make embeddings relatively larger
        #print(f"In encoder: {x.shape}")
        x = x * math.sqrt(self.d_model)
        #add constant to embedding
        seq_len = x.size(1)
        x = x + Variable(self.pe[:,:seq_len], \
        requires_grad=False).cuda()
        return x

def flipTensor(b):
  zero_indices = b == 0
  non_zero_indices = b != 0
  b[non_zero_indices] = -1
  b[zero_indices] = 1
  b[non_zero_indices] = 0

  return b

class NMTModel(nn.Module):
  def __init__(self, embedding_size, src_vocab_size, tgt_vocab_size, num_heads, num_encoder_layers, num_decoder_layers, dropout, max_len_eng, max_len_cyp, device):
    
    super(NMTModel, self).__init__()
    self.src_embedding = nn.Embedding(src_vocab_size, embedding_size)
    self.tgt_embedding = nn.Embedding(tgt_vocab_size, embedding_size)

    self.src_pos_encoding = PositionalEncoder(embedding_size, max_len_eng)
    self.tgt_pos_encoding = PositionalEncoder(embedding_size, max_len_cyp)

    self.device = device
    self.transformer = nn.Transformer(d_model = embedding_size, nhead = num_heads, num_encoder_layers = num_encoder_layers, num_decoder_layers = num_decoder_layers, dropout = dropout)

    self.fc = nn.Linear(embedding_size, tgt_vocab_size)
    self.dropout = dropout

  def generate_square_subsequent_mask(self, sz):
    mask = (torch.triu(torch.ones((sz, sz))) == 1).transpose(0, 1)
    mask = mask.float().masked_fill(mask == 0, float('-inf')).masked_fill(mask == 1, float(0.0))
    return mask.to(device)

  def forward(self, eng_input_ids, eng_attention_mask, cyp_input_ids, cyp_attention_mask):
    
    decoder_mask = self.mask_cyp = self.generate_square_subsequent_mask(128)

    src_emb = self.src_pos_encoding(self.src_embedding(eng_input_ids))
    tgt_emb = self.tgt_pos_encoding(self.tgt_embedding(cyp_input_ids))

    src_emb = torch.transpose(src_emb, 1, 0)
    tgt_emb = torch.transpose(tgt_emb, 1, 0)

    src_mask = torch.zeros((128, 128),device=device).type(torch.bool)

    eng_attention_mask = flipTensor(eng_attention_mask)
    cyp_attention_mask = flipTensor(cyp_attention_mask)

    out = self.transformer(src = src_emb, tgt = tgt_emb, src_mask = None, tgt_mask = decoder_mask, src_key_padding_mask = eng_attention_mask, tgt_key_padding_mask = cyp_attention_mask)

    return self.fc(out)

embedding_size = 256 
src_vocab_size = english_tokenizer.get_vocab_size() 
tgt_vocab_size = cypher_tokenizer.get_vocab_size() 
num_heads = 8 
num_encoder_layers = 8 
num_decoder_layers = 8 
dropout = 0.2 
max_len_eng = 128 
max_len_cyp = 128 
PAD_IDX = 3

model = NMTModel(embedding_size, src_vocab_size, tgt_vocab_size, num_heads, num_encoder_layers, num_decoder_layers, dropout, max_len_eng, max_len_cyp, device)

for p in model.parameters():
    if p.dim() > 1:
        nn.init.xavier_uniform_(p)

model = model.to(device)

loss_fn = torch.nn.CrossEntropyLoss(ignore_index=PAD_IDX)

optimizer = torch.optim.Adam(model.parameters(), lr=0.000001)

from nltk.translate.bleu_score import sentence_bleu

def bleu_score(logits, cyp_input_ids):
  y_trans = torch.transpose(logits, 0, 1)
  predict = torch.argmax(y_trans, dim = 2)
  true_cypher = []
  predicted_cypher = []
  bleu_sc = 0

  for i in range(y_trans.shape[0]):
    #true_cypher.append(cypher_tokenizer.decode(cyp_input_ids[i].tolist()))
    #predicted_cypher.append(cypher_tokenizer.decode(predict[i].tolist()))
    bleu_sc = bleu_sc + sentence_bleu([cypher_tokenizer.decode(cyp_input_ids[i].int().tolist())], cypher_tokenizer.decode(predict[i].int().tolist()))

  return bleu_sc/y_trans.shape[0]

def train_model(model, epochs):

  trainLosses=[]
  validLosses=[]
  avgTrainLoss=[]
  avgValidLoss=[]

  for i in range(epochs):
    print("Epoch: ", i)

    train_loss = 0
    val_loss = 0
    
    model.train()

    for batch_idx, (eng_input_ids, eng_attention_mask, cyp_input_ids, cyp_attention_mask) in enumerate(trainLoader):
      
      if batch_idx % 200 == 0:
        print(batch_idx)

      eng_input_ids = eng_input_ids.to(device)
      eng_attention_mask = eng_attention_mask.to(device, dtype=torch.bool)
      cyp_input_ids = cyp_input_ids.to(device)
      cyp_attention_mask = cyp_attention_mask.to(device, dtype=torch.bool)

      optimizer.zero_grad()

      logits = model(eng_input_ids.long(), eng_attention_mask, cyp_input_ids.long(), cyp_attention_mask)

      #print(logits)

      loss = loss_fn(logits.reshape(-1, logits.shape[-1]), cyp_input_ids.reshape(-1).long())
      loss.backward()

      train_loss = train_loss + loss

      torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1)

      optimizer.step()

    trainLosses.append(train_loss/len(trainLoader))

    print("Validating...")
    model.eval()
    with torch.no_grad():
      bleu_sc = 0

      for batch_idx, (eng_input_ids, eng_attention_mask, cyp_input_ids, cyp_attention_mask) in enumerate(valLoader):

        eng_input_ids = eng_input_ids.to(device)
        eng_attention_mask = eng_attention_mask.to(device, dtype=torch.bool)
        cyp_input_ids = cyp_input_ids.to(device)
        cyp_attention_mask = cyp_attention_mask.to(device, dtype=torch.bool)

        logits = model(eng_input_ids.long(), eng_attention_mask, cyp_input_ids.long(), cyp_attention_mask)

        bleu_sc = bleu_sc + bleu_score(logits, cyp_input_ids)

        loss = loss_fn(logits.reshape(-1, logits.shape[-1]), cyp_input_ids.reshape(-1).long())
        val_loss = val_loss + loss

      validLosses.append(val_loss/len(valLoader))

    print("Epoch: ", i, " Training Loss: ", (train_loss/len(trainLoader)), " Val Loss: ", (val_loss/len(valLoader)), "BLEU Score: ", (bleu_sc/len(valLoader)))

  return model, trainLosses, validLosses

model, train_loss, valid_loss = train_model(model, 10)

bleu_sc = 0
model.eval()

with torch.no_grad():
  for batch_idx, (eng_input_ids, eng_attention_mask, cyp_input_ids, cyp_attention_mask) in enumerate(testLoader):

    eng_input_ids = eng_input_ids.to(device)
    eng_attention_mask = eng_attention_mask.to(device, dtype=torch.bool)
    cyp_input_ids = cyp_input_ids.to(device)
    cyp_attention_mask = cyp_attention_mask.to(device, dtype=torch.bool)

    logits = model(eng_input_ids.long(), eng_attention_mask, cyp_input_ids.long(), cyp_attention_mask)

    bleu_sc = bleu_sc + bleu_score(logits, cyp_input_ids)

print("BLEU Score on test set: ", (bleu_sc/len(testLoader)))

epochs = range(1,len(train_loss)+1)
plt.plot(epochs, train_loss, 'g', label='Training loss')
plt.plot(epochs, valid_loss, 'b', label='Validation loss')
plt.title('Training and Validation loss')
plt.xlabel('Epochs')
plt.ylabel('Loss')
plt.legend()
plt.savefig('Loss', bbox_inches='tight')
plt.close()
#plt.show()