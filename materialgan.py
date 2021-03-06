# -*- coding: utf-8 -*-
"""materialGAN.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1hsKMLMhO7HYXiaWdWb3doOMJJx4FjWYC
"""

# Commented out IPython magic to ensure Python compatibility.
import os
import random
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim as optim
import torch.utils.data
import torchvision.datasets as dset
import torchvision.transforms as transforms
import torchvision.utils as vutils
import torchvision.models as models
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
import copy
from PIL import Image
from torch.autograd import Variable
import time
import warnings
from matplotlib.ticker import FuncFormatter

warnings.filterwarnings('ignore')

# %matplotlib inline

manual_seed = int(time.time())
print("Random Seed: ", manual_seed)
random.seed(manual_seed)
torch.manual_seed(manual_seed)

# location of folder
dataroot = "drive/MyDrive/SuperFolderTrainData"
# number of workers
workers = 2
# batch size for training
batch_size = 30
# image size for input
image_size = 128
# number of channel (1 for BW, 3 for RGB)
nc = 3
# Size of z latent vector (i.e. size of generator input)
nz = 16
# Size of feature maps in generator
ngf = 128
# Size of feature maps in discriminator
ndf = 128
# Number of training epochs
num_epochs = 50
# Learning rate for optimizers
lr = 0.0005
# Style loss weight
sl_loss_weight = 0.03
# Colapse loss weight
cl_loss_weight = 0.03
# Beta values hyperparam for Adam optimizers
beta1 = 0.5
beta2 = 0.99
# Number of GPUs available, currently running on CPU
ngpu = 1
 
print(torch.cuda.get_device_name(torch.cuda.current_device()))

# define weights for layer and normalisation
def weights_init(m):
    classname = m.__class__.__name__
    if classname.find('Conv')!=-1:
        nn.init.normal_(m.weight.data, 0.0, 0.02)
    elif classname.find('BatchNorm')!=-1:
        nn.init.normal_(m.weight, 1.0, 0.02)
        nn.init.constant_(m.bias.data, 0)

# setup dataset and data loader
dataset = dset.ImageFolder(root=dataroot, transform=transforms.Compose([transforms.Resize(image_size), 
                                                                        transforms.CenterCrop(image_size),
                                                                        transforms.ToTensor(),
                                                                        transforms.Normalize((0.5,),(0.5,))]))
 
dataloader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=workers)
 
device = torch.device("cuda:0" if(torch.cuda.is_available() and ngpu>0) else "cpu")

class Generator(nn.Module):
  def __init__(self, ngpu):
    super(Generator, self).__init__()
    self.ngpu = ngpu
    self.main = nn.Sequential()
    
    # input z into convolution
    self.main.add_module('conv1', nn.ConvTranspose2d(nz, ngf*8, 8, 2, 0, bias=False))
    self.main.add_module('btch1', nn.BatchNorm2d(ngf*8))
    self.main.add_module('relu1', nn.ReLU(True))

    # state ngf * 8 * 8
    self.main.add_module('conv2', nn.ConvTranspose2d(ngf*8, ngf*4, 4, 2, 1, bias=False))
    self.main.add_module('btch2', nn.BatchNorm2d(ngf*4))
    self.main.add_module('relu2', nn.ReLU(True))
            
    # state ngf/2 * 16*16
    self.main.add_module('conv3', nn.ConvTranspose2d(ngf*4, ngf*2, 4, 2, 1, bias=False))
    self.main.add_module('btch3', nn.BatchNorm2d(ngf*2))
    self.main.add_module('relu3', nn.ReLU(True))
            
    # state ngf/4 * 32*32
    self.main.add_module('conv4', nn.ConvTranspose2d(ngf*2, ngf, 4, 2, 1, bias=False))
    self.main.add_module('btch4', nn.BatchNorm2d(ngf))
    self.main.add_module('relu4', nn.ReLU(True))
            
    # state ngf/8 *64*64
    self.main.add_module('conv5', nn.ConvTranspose2d(ngf, nc, 4, 2, 1, bias=False))
    self.main.add_module('output', nn.Tanh())
        
    #state 1 *128*128
        
  def forward(self, input):
    return self.main(input)


# Create the generator
netG = Generator(ngpu).to(device)
 
# Handle multi-gpu if desired
if (device.type == 'cuda') and (ngpu > 1):
  netG = nn.DataParallel(netG, list(range(ngpu)))
 
# Apply the weights_init function to randomly initialize all weights
#  to mean=0, stdev=0.2.
netG.apply(weights_init)
 
# Print the model
print(netG)

# Access a particular layer
#print(netG.main.conv1)

# Get tensor of the layer
#print(netG.main.conv1.weight)

class Discriminator(nn.Module):
  def __init__(self, ngpu):
    super(Discriminator, self).__init__()
    self.ngpu = ngpu
    self.main = nn.Sequential()

    # input is (nc) *128*128
    self.main.add_module('conv1', nn.Conv2d(nc, ndf, 4, 2, 1, bias=False))
    self.main.add_module('relu1', nn.LeakyReLU(0.2, inplace=True))

    # input is ndf/8 *64*64
    self.main.add_module('conv2', nn.Conv2d(ndf, ndf*2, 4, 2, 1, bias=False))
    self.main.add_module('btch2', nn.BatchNorm2d(ndf*2))
    self.main.add_module('relu2', nn.LeakyReLU(0.2, inplace=True))

    #input is ndf/4 *32*32
    self.main.add_module('conv3', nn.Conv2d(ndf*2, ndf*4, 4, 2, 1, bias=False))
    self.main.add_module('btch3', nn.BatchNorm2d(ndf*4))
    self.main.add_module('relu3', nn.LeakyReLU(0.2, inplace=True))

    #input is ndf/2 *16*16
    self.main.add_module('conv4', nn.Conv2d(ndf*4, ndf*8, 4, 2, 1, bias=False))
    self.main.add_module('btch4', nn.BatchNorm2d(ndf*8))
    self.main.add_module('relu4', nn.LeakyReLU(0.2, inplace=True))

    #input is ndf *8*8
    self.main.add_module('conv5', nn.Conv2d(ndf*8, 1, 8, 1, 0, bias=False))
    self.main.add_module('output', nn.Sigmoid())

  def forward(self, input):
    return self.main(input), self.main.conv5

# Create the Discriminator
netD = Discriminator(ngpu).to(device)
 
# Handle multi-gpu if desired
if (device.type == 'cuda') and (ngpu > 1):
  netD = nn.DataParallel(netD, list(range(ngpu)))
 
# Apply the weights_init function to randomly initialize all weights
#  to mean=0, stdev=0.2.
netD.apply(weights_init)
 
# Print the model
print(netD)

def gram_matrix(input):
  a, b, c, d = input.size() # a=batch size(=1) b=number of feature maps (c,d)=dimensions of a f. map (N=c*d)
  features = input.view(a * b, c * d) # resise F_XL into \hat F_XL
  G = torch.mm(features, features.t()) # compute the gram product
  return G.div(a * b * c * d) # we 'normalize' the values of the gram matrix by dividing by the number of element in each feature maps.

def style_loss(style_layer, combination_layer, num_channels = nc):
  assert style_layer.size()==combination_layer.size(), "Input Sizes do not match in StyleLoss"
  a, b, c, d = style_layer.size() # a=batch size(=1) b=number of feature maps (c,d)=dimensions of a f. map (N=c*d)
  styleloss = 0
  
  for i in range(a):
    S = gram_matrix(torch.unsqueeze(style_layer[i], 0)).detach()
    C = gram_matrix(torch.unsqueeze(combination_layer[i],0)).detach()
    styleloss = torch.add(styleloss, torch.sum(torch.square(S-C)/(2*num_channels*c*d)**2)*3e8)
    styleloss = Variable(styleloss, requires_grad=True)

  return styleloss

def colapse_loss(target_feature):
  z_d_gen = torch.flatten(target_feature).reshape(1,-1)
  nom = torch.mm(z_d_gen, z_d_gen.t())
  denom = torch.sqrt(torch.sum(torch.square(z_d_gen), 1, keepdim=True))
  pt = torch.square(torch.transpose((nom / denom), 1, 0))
  #pt = pt - torch.diag(torch.diag(pt))
  pulling_term = torch.sum(pt) / (batch_size * (batch_size - 1)*4e1)
  pulling_term = Variable(pulling_term, requires_grad=True)

  return pulling_term

vgg19 = models.vgg19(pretrained=True).features.to(device).eval()

def get_vgg_layers(input, model=vgg19, num_layer=4):
  i = 0
  Model = copy.deepcopy(model)
  list_layers = nn.ModuleList()
  module = None
  for layer in Model.children():
    if isinstance(layer, nn.Conv2d):
      i +=1
      name = 'conv{}'.format(i)
      list_layers.append(module)
      module = nn.Sequential()
    elif isinstance(layer, nn.ReLU):
      name = 'relu{}'.format(i)
    elif isinstance(layer, nn.MaxPool2d):
      name = 'pool{}'.format(i)
    elif isinstance(layer, nn.BatchNorm2d):
      name = 'btnm{}'.format(i)
    else: 
      raise RuntimeError('Unrecognized layer: {}'.format(layer.__class__.__name__))

    module.add_module(name, layer)

    if i >= (num_layer+1):
      break

  outconv1 = list_layers[1](input)
  outconv2 = list_layers[2](outconv1)
  outconv3 = list_layers[3](outconv2)
  outconv4 = list_layers[4](outconv3)

  return outconv1, outconv2, outconv3, outconv4

# Visualise images and feature maps applied over them
loader = transforms.Compose([transforms.Resize(image_size), transforms.CenterCrop(image_size),
                             transforms.ToTensor()])
 
#Style Image
StyleImage = "drive/My Drive/SuperFolderTrainData/TrainData/5399.jpg"
style_image = Image.open(StyleImage)
style_image = loader(style_image)[:3,:,:].unsqueeze(0)

Sconv1, Sconv2, Sconv3, Sconv4 = get_vgg_layers(style_image.to(device, torch.float))
print('SConv1 shape: {}'.format(Sconv1.shape))
print('SConv2 shape: {}'.format(Sconv2.shape))
print('SConv3 shape: {}'.format(Sconv3.shape))
print('SConv4 shape: {}'.format(Sconv4.shape))

visuals = [
    ('Soriginal', style_image),
    ('Sconv1', Sconv1),
    ('Sconv2', Sconv2),
    ('Sconv3', Sconv3),
    ('Sconv4', Sconv4)]

plt.figure(figsize=(15,20))
for i in range(5):
  plt.subplot(1,5,i+1)
  if(i==0):
    plt.imshow(visuals[i][1].squeeze().permute(1,2,0))
  else:
    for j in range(visuals[i][1].squeeze().shape[0]):
      plt.imshow(visuals[i][1].squeeze().cpu().detach().numpy()[j])
  plt.title(visuals[i][0])

def get_style_colapse_loss(style_batch, gen_batch):
  Sconv1, Sconv2, Sconv3, Sconv4 = get_vgg_layers(style_batch)
  Cconv1, Cconv2, Cconv3, Cconv4 = get_vgg_layers(gen_batch)

  #Sconv1.detach_()
  #Sconv2.detach_()
  #Sconv3.detach_()
  #Sconv4.detach_()
  #Cconv1.detach_()
  #Cconv2.detach_()
  #Cconv3.detach_()
  #Cconv4.detach_()

  # style loss
  s1 = style_loss(Sconv1, Cconv1)
  s2 = style_loss(Sconv2, Cconv2)
  s3 = style_loss(Sconv3, Cconv3)
  s4 = style_loss(Sconv4, Cconv4)
  sl_loss = torch.mean(s1+s2+s3+s4)
  
  Cconv = torch.cat((torch.flatten(Cconv1), torch.flatten(Cconv2), torch.flatten(Cconv3), torch.flatten(Cconv4)), 0)
  # colapse loss
  #c1 = colapse_loss(Cconv1)
  #c2 = colapse_loss(Cconv2)
  #c3 = colapse_loss(Cconv3)
  #c4 = colapse_loss(Cconv4)
  c = colapse_loss(Cconv)
  cl_loss = torch.mean(c) #############(c1+c2+c3+c4)

  return sl_loss, cl_loss

# Initialize BCELoss function
Dcriterion = nn.BCELoss()
Gcriterion = nn.BCELoss()
 
# Create batch of latent vectors that we will use to visualize
#  the progression of the generator
fixed_noise = torch.randn(128, nz, 1, 1, device=device)
 
# Establish convention for real and fake labels during training
real_label = 0.
fake_label = 1.
 
# Setup Adam optimizers for both G and D
optimizerD = optim.Adam(netD.parameters(), lr=lr, betas=(beta1, beta2), weight_decay=0.3)
optimizerG = optim.Adam(netG.parameters(), lr=lr, betas=(beta1, beta2), weight_decay=0.3)

# Training loop
img_list = [] #stores prgressive images produced by generator
G_losses = [] #stores progressive losses by generator
D_losses = [] #stores progressive losses by discriminator
G_steps = 1 #train generator in every G_step
D_steps = 3 #train discriminator in every D_step
iter = 0 #track iteration

print('Starting Training')
for epoch in tqdm(range(num_epochs)):
  for i, data in enumerate(dataloader):
    D_realx, D_fakex, D_fakex2 = 0.0, 0.0, 0.0
    errD, errD_real, errD_fake = None, None, None
    fake_x = None
    # Train discriminator
    if i%D_steps==0:
      ############# REAL DATA ###############
      netD.zero_grad() # Reset gradients
      real_x = data[0].to(device) # Load real data
      b_size = real_x.size(0) # Batch size, should be equal to 30 as set earlier
      label = torch.full((b_size,), real_label, dtype=torch.float, device=device) # Set real labels
      output = netD(real_x)[0].view(-1) # Pass real data through discriminator, flatten to keep columns fixed, i.e, b_size

      errD_real = Dcriterion(output, label) # Calculate loss on real data
      errD_real.backward() #Compute gradients

      D_realx = output.mean().item() # Mean output by discriminator over real data

      ############# FAKE DATA ###############
      noise = torch.randn(b_size, nz, 1, 1, device=device) # Generate noise data of b_size
      fake_x = netG(noise) # Create fake images
      label.fill_(fake_label) # Add labels that the data is fake
      output = netD(fake_x.detach())[0].view(-1) # Pass fake data through discriminator, flatten to keep columns fixed, i.e, b_size

      errD_fake = Dcriterion(output, label) # Calculate loss on fake data
      errD_fake.backward() #Compute gradients

      D_fakex = output.mean().item()

      ############# OPTIMIZE DISCRIMINATOR ###############
      errD = errD_real + errD_fake #Adds Gradients as well
      optimizerD.step() # Optimize

    #Train Generator
    netG.zero_grad()
    if i%D_steps != 0:
      real_x = data[0].to(device)
      label = torch.full((b_size,), real_label, dtype=torch.float, device=device)
      noise = torch.randn(b_size, nz, 1, 1, device=device) # Generate noise data of b_size
      fake_x = netG(noise) # Create fake images
      output = netD(fake_x)[0].view(-1) # Pass fake data through discriminator, flatten to keep columns fixed, i.e, b_size

    else:
      label.fill_(real_label)
      output = netD(fake_x)[0].view(-1)

    errG_bce = Gcriterion(output, label)
    errG_bce.backward()
    D_fakex2 = output.mean().item()

    sl_loss, cl_loss = get_style_colapse_loss(real_x, fake_x)
    sl_loss *= sl_loss_weight
    sl_loss.backward()

    cl_loss *= cl_loss_weight
    cl_loss.backward()

    errG = errG_bce + sl_loss + cl_loss
    optimizerG.step()

    #Output for training stats
    if i%60 == 0:
      print('Epoch/Num Epochs: {}/{} | ErrorD: {} | ErrorG: {} | D(realx): {} | D(fakex): {} | D(fakex2): {}'.format(epoch, num_epochs,
                                                                                                                    errD.item(),errG.item(),
                                                                                                                  D_realx,D_fakex,D_fakex2))
      
      print('errD_real: {} | errD_fake: {} | errG_bce: {} | SLoss: {} | CLoss: {}'.format(errD_real.item(),errD_fake.item(),
                                                                                          errG_bce.item(),
                                                                                          sl_loss.item(),
                                                                                          cl_loss.item()))

    # Record Losses
    if i%3==0:
      G_losses.append(errG.item())
      D_losses.append(errD.item())

    if iter%500 == 0:
      with torch.no_grad():
        fake = netG(fixed_noise).detach().cpu()
      img_list.append(fake)

    iter += 1

plt.figure(figsize=(10,5))
plt.title("Generator and Discriminator Loss During Training")
plt.plot(G_losses,label="G")
plt.plot(D_losses,label="D")
plt.xlabel("iterations")
plt.ylabel("Loss")
plt.legend()
plt.gca().get_xaxis().set_major_formatter(FuncFormatter(lambda x, p: format(int(x*3), ',')))
plt.show()

plt.figure(figsize=(30,10))
for i in range(len(img_list)):
  plt.subplot(2,len(img_list)/2,i+1)
  plt.imshow(img_list[i].mean(0).mean(0))#, cmap='gray')
  plt.title('{}'.format(i*500))
plt.show()

plt.imshow(np.random.rand(128,128,3))

torch.save(netG.state_dict(), '/content/drive/MyDrive/netG.pt')

torch.save(netD.state_dict(), '/content/drive/MyDrive/netD.pt')

