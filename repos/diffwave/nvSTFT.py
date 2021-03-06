import math
import os
os.environ["LRU_CACHE_CAPACITY"] = "3"
import random
import torch
import torch.utils.data
import numpy as np
import librosa
from librosa.util import normalize
from librosa.filters import mel as librosa_mel_fn
from scipy.io.wavfile import read
try:
    import soundfile as sf
except:
    sf = None

def load_wav_to_torch(full_path, target_sr=22050):
    if full_path.endswith('wav') and sf is not None:
        sampling_rate, data = read(full_path) # scipy only supports .wav but reads faster...
    else:
        data, sampling_rate = sf.read(full_path, always_2d=True)[:,0] # than soundfile.
    
    if np.issubdtype(data.dtype, np.integer): # if audio data is type int
        max_mag = -np.iinfo(data.dtype).min # maximum magnitude = min possible value of intXX
    else: # if audio data is type fp32
        max_mag = max(np.amax(data), -np.amin(data))
        max_mag = (2**31)+1 if max_mag > (2**15) else ((2**15)+1 if max_mag > 1.01 else 1.0) # data should be either 16-bit INT, 32-bit INT or [-1 to 1] float32
    
    data = torch.FloatTensor(data.astype(np.float32))/max_mag
    
    if sampling_rate != target_sr:
        data = torch.from_numpy(librosa.core.resample(data.numpy(), sampling_rate, target_sr))
        sampling_rate = target_sr
    
    return data, sampling_rate

def dynamic_range_compression(x, C=1, clip_val=1e-5):
    return np.log(np.clip(x, a_min=clip_val, a_max=None) * C)

def dynamic_range_decompression(x, C=1):
    return np.exp(x) / C

def dynamic_range_compression_torch(x, C=1, clip_val=1e-5):
    return torch.log(torch.clamp(x, min=clip_val) * C)

def dynamic_range_decompression_torch(x, C=1):
    return torch.exp(x) / C

class STFT():
    def __init__(self, sr=22050, n_mels=80, hop_length=256, fmin=20):
        self.target_sr = sr
        self.hop_length = hop_length
        self.n_mels = n_mels
        self.fmin = fmin
        self.mel_basis = {}
        self.hann_window = {}
    
    def get_mel(self, y, n_fft=1024, sampling_rate=22050, win_size=1024, fmax=11025, center=False):
        hop_length = self.hop_length
        n_mels     = self.n_mels
        fmin       = self.fmin
        
        if torch.min(y) < -1.:
            print('min value is ', torch.min(y))
        if torch.max(y) > 1.:
            print('max value is ', torch.max(y))
        
        if fmax not in self.mel_basis:
            mel = librosa_mel_fn(sampling_rate, n_fft, n_mels, fmin, fmax)
            self.mel_basis[str(fmax)+'_'+str(y.device)] = torch.from_numpy(mel).float().to(y.device)
            self.hann_window[str(y.device)] = torch.hann_window(1024).to(y.device)
        
        y = torch.nn.functional.pad(y.unsqueeze(1), (int((n_fft-hop_length)/2), int((n_fft-hop_length)/2)), mode='reflect')
        y = y.squeeze(1)
        
        spec = torch.stft(y, n_fft, hop_length=hop_length, win_length=win_size, window=self.hann_window[str(y.device)],
                          center=center, pad_mode='reflect', normalized=False, onesided=True)
        
        spec = torch.sqrt(spec.pow(2).sum(-1)+(1e-9))
        
        spec = torch.matmul(self.mel_basis[str(fmax)+'_'+str(y.device)], spec)
        spec = dynamic_range_compression_torch(spec)
        return spec
    
    def __call__(self, audiopath):
        audio, sr = load_wav_to_torch(audiopath, target_sr=22050)
        spect = self.get_mel(audio.unsqueeze(0)).squeeze(0)
        return spect

stft = STFT()