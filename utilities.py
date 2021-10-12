import dearpygui.dearpygui as dpg
import os
from tables import Tables

#Tacotron imports
import os
from dearpygui.dearpygui import get_value
import sys
import numpy as np
# import tables
import torch
sys.path.append('tacotron2/waveglow/')
sys.path.insert(1, '/tacotron2')
from hparams import create_hparams
from model import Tacotron2
from layers import TacotronSTFT, STFT
from audio_processing import griffin_lim
from train import load_model
from text import text_to_sequence
from denoiser import Denoiser
import subprocess
import threading
import time
from pydub import AudioSegment 
from pydub.playback import play
import soundfile as sf
import simpleaudio as sa

dpg.create_context()


class Trainer():
    def __init__(self):
        self.process = None
        self.is_training_running = False
        self.t1 = None
        self.t2 = None     
        self.hifigan_checkpoint_name = None
        self.hifigan_project_name = None 
        self.tensorboard_process = None
    
    def set_tensorboard_process(self, p):
        self.tensorboard_process = p

    def get_tensorboard_process(self):
        return self.tensorboard_process

    def set_hifigan_checkpoint_name(self, path):
        self.hifigan_checkpoint_name = path    

    def get_hifigan_checkpoint_name(self):
        return self.hifigan_checkpoint_name

    def set_hifigan_project_name(self, path):
        self.hifigan_project_name = path    

    def get_hifigan_project_name(self):
        return self.hifigan_project_name

    def is_running(self):
        return self.is_training_running

    def train_taco(self):
        dpg.set_value("shell_output_tacotron2", None)

    def train_waveglow(self):
        pass

    def train_hifigan(self):
        self.is_training_running = True
        os.chdir("hifi-gan")      

        def start_process():
            print(self.hifigan_checkpoint_name)
            print(self.hifigan_project_name)
           
            self.process =  subprocess.Popen(['python', '-u', 'train.py', '--checkpoint_path', self.hifigan_checkpoint_name,
            '--input_training_file', self.hifigan_project_name + '/' + 'training.csv', '--input_validation_file', self.hifigan_project_name + '/' + 'validation.csv', '--input_wavs_dir', self.hifigan_project_name + '/' + 'wavs'] , stdout=subprocess.PIPE)  
                       
            # self.process =  subprocess.Popen(['python', '-u', 'train.py', '--checkpoint_path', 'attenborough.model',
            # '--input_training_file', 'training.csv', '--input_validation_file', 'validation.csv', '--input_wavs_dir', 'wavs'] , stdout=subprocess.PIPE)  
           
            # self.process =  subprocess.run(['python', '-u', 'train.py', '--checkpoint_path', 'attenborough.model',
            # '--input_training_file', 'training.csv', '--input_validation_file', 'validation.csv', '--input_wavs_dir', 'wavs'] , capture_output=True, text=True)  

            os.chdir("../")

            while self.is_training_running:
                time.sleep(.01)
                out = self.process.stdout.readline().decode('utf-8')
                if out: 
                    print(out)
                    dpg.set_value("shell_output_hifigan", out)

        self.t1 = threading.Thread(target=start_process)

        self.t1.start()

        print("HifiGan training started!")
        dpg.set_value("shell_output_hifigan", "HifiGan training started. Check console for more information.")


    def stop_training_hifigan(self):
        print("\nStopping hifigan training... waiting for epoch to end...")
        with open("training_status.txt", 'w') as f:
            f.write("terminate")
        if self.process:
            self.process.kill()
            time.sleep(1)
            self.is_training_running = False
            dpg.set_value("shell_output_hifigan", "training stopped.")
            print("Training stopped successfully.")
            if os.path.exists("hifi-gan/training_status.txt"):
                f = open("hifi-gan/training_status.txt", 'w')
                f.close()                                   
            # os.chdir("../")

        

    def stop_training_tacotron2(self):
        pass
        # with open ("hifi-gan/training_status.txt", 'w') as f:
        #     pass
        # if self.process:
        #     self.process.kill()
        #     print("hifigan training has ended")
        #     dpg.set_value("shell_output_tacotron2", "training stopped.")
       
    def stop_training_waveglow(self):
        pass
        # with open ("waveglow/training_status.txt", 'w') as f:
        #     pass
        # if self.process:
        #     self.process.kill()
        #     print("hifigan training has ended")
        #     dpg.set_value("shell_output_waveglow", "training stopped.")



class Inferer():
    def __init__(self):
        self.taco_model_name = None
        self.taco_model_path = None
        self.waveglow_model_name = None
        self.waveglow_model_path = None
        self.hifigan_model_name = None
        self.hifigan_model_path = None
        self.taco_model = None
        self.waveglow_model = None
        self.hifigan_model = None
        self.denoiser = None
        self.text_file_path = None
        self.file_count = 0
       
        self.table_array = np.empty([0,2])
        with dpg.table(scrollY=True, row_background=True, borders_innerH=True, borders_outerH=True, borders_innerV=True,
                            borders_outerV=True, parent="inference_tab", header_row=True, width=1100, height=400, tag="infer_table"):
            dpg.add_table_column(width_fixed=True, init_width_or_weight=700, parent="infer_table", label='TEXT')
            dpg.add_table_column(width_fixed=True, init_width_or_weight=200, parent="infer_table", label='AUDIO FILE')
            dpg.add_table_column(width_fixed=True, init_width_or_weight=200, parent="infer_table", label='OPTIONS')
    
    def show_table(self):
        # clear table
        dpg.delete_item("infer_table")
        with dpg.table(scrollY=True, row_background=True, borders_innerH=True, borders_outerH=True, borders_innerV=True,
                            borders_outerV=True, parent="inference_tab", header_row=True, width=1100, height=400, tag="infer_table"):
            dpg.add_table_column(width_fixed=True, init_width_or_weight=700, parent="infer_table", label='TEXT')
            dpg.add_table_column(width_fixed=True, init_width_or_weight=200, parent="infer_table", label='AUDIO FILE')
            dpg.add_table_column(width_fixed=True, init_width_or_weight=200, parent="infer_table", label='OPTIONS')        
        l = len(self.table_array)
        for i in range(0, l):    
            with dpg.table_row(parent="infer_table"): 

                dpg.add_input_text(tag="input_text_" + str(i), default_value=str(self.table_array[i][0]), width=700)
                dpg.add_text(str(self.table_array[i][1]), tag="wav_path_" + str(i))

                a_path = str(self.table_array[i][1])
                entry_info = {
                    "rank": i,
                    "text": dpg.get_value("input_text_" + str(i))
                }

                with dpg.group(horizontal=True):
                    dpg.add_button(label="Play", callback=self.callback_play_entry, user_data = a_path)
                    dpg.add_button(label="Redo", callback=self.callback_redo_entry, user_data = entry_info)
                    dpg.add_button(label="Remove", callback=self.callback_remove_entry, user_data = i)

    def add_entry(self, entry):
        self.table_array = np.vstack((self.table_array, entry))
        self.show_table()

    def callback_play_entry(self, sender, app_data, user_data):
        self.stop()
        a = AudioSegment.from_file(user_data)    
        t_play = threading.Thread(target=self.play, args=(a,))
        t_play.start()

    def callback_redo_entry(self, sender, app_data, user_data):
        self.stop()
        text = dpg.get_value("input_text_" + str(user_data["rank"]))
        #run inference again
        result = self.run_inference(text, "text_input", "wavs_out/" + str(user_data["rank"]) + ".wav")
        a = AudioSegment.from_file(result[0])    
        t_play = threading.Thread(target=self.play, args=(a,))
        t_play.start()      


    def callback_remove_entry(self, sender, app_data, user_data):
        self.stop()
        pass
    
    def play(self, data):
        wav = data            
        sa.play_buffer(
            wav.raw_data,
            num_channels=wav.channels,
            bytes_per_sample=wav.sample_width,
            sample_rate=wav.frame_rate
        )

    def stop(self):
        sa.stop_all()

    def set_taco_model_path(self, path):
        self.taco_model_path = path
    def set_waveglow_model_path(self, path):
        self.waveglow_model_path = path
    def set_hifigan_model_path(self, path):
        self.hifigan_model_path = path
    def set_text_file_path(self, path):
        self.text_file_path = path

    def get_text_file_path(self):
        return self.text_file_path
    def get_hifigan_model_path(self):
        return self.hifigan_model_path

    def run_inference(self, input_text, mode, wav_path):
        if not os.path.exists("wavs_out"):
            os.mkdir("wavs_out")
        hparams = create_hparams()
        hparams.sampling_rate = 22050
        #hparams change dropouts!  
        hparams.p_attention_dropout = 0
        hparams.p_decoder_dropout = 0
        hparams.max_decoder_steps = 10000
   
        self.taco_model = load_model(hparams)
        self.taco_model.load_state_dict(torch.load(self.taco_model_path)['state_dict'])
        _ = self.taco_model.cuda().eval().half()
        self.waveglow_model = torch.load(self.waveglow_model_path)['model']
        self.waveglow_model.cuda().eval().half()
        for k in self.waveglow_model.convinv:
            k.float()
        self.denoiser = Denoiser(self.waveglow_model)
        #text = "a log file will be created when first opening a project. The last entry that was edited is recorded, so that work can easily be resumed."
        if mode == "text_input":
            text = input_text
            sequence = np.array(text_to_sequence(text, ['english_cleaners']))[None, :]
            sequence = torch.autograd.Variable(torch.from_numpy(sequence)).cuda().long()
            mel_outputs, mel_outputs_postnet, _, alignments = self.taco_model.inference(sequence)
            
            with torch.no_grad():
                audio = self.waveglow_model.infer(mel_outputs_postnet, sigma=1)
            audio_denoised = self.denoiser(audio, strength=0.02)[:, 0]
            audioout = audio_denoised[0].data.cpu().numpy()
            #audioout = audio[0].data.cpu().numpy()
            audioout32 = np.float32(audioout)  
            if wav_path:
                wav_name = wav_path
            else:  
                wav_name = 'wavs_out/' + str(self.file_count) + '.wav'
            sf.write(wav_name, audioout32, 22050)
            return [wav_name]

            # a = AudioSegment.from_file(wav_name) 
            # t_play = threading.Thread(target=self.play, args=(a,))
            # t_play.start()
            # entry = np.array([text, wav_name])
            # self.add_entry([entry])
            # self.file_count += 1

        elif mode == "text_input_file":
            #break text apart and infer each phrase.
            #get max word length of phrase if no punctuation
            import re
            phrase_splits = re.split(r'(?<=[\.\!\?])\s*', input_text)   #split on white space between sentences             
            phrase_splits = list(filter(None, phrase_splits))  #remove empty splits
            if phrase_splits:
                result = []
                for i, p in enumerate(phrase_splits):
                    text = p
                    sequence = np.array(text_to_sequence(text, ['english_cleaners']))[None, :]
                    sequence = torch.autograd.Variable(torch.from_numpy(sequence)).cuda().long()
                    mel_outputs, mel_outputs_postnet, _, alignments = self.taco_model.inference(sequence)
                    
                    with torch.no_grad():
                        audio = self.waveglow_model.infer(mel_outputs_postnet, sigma=1)
                    audio_denoised = self.denoiser(audio, strength=0.02)[:, 0]
                    audioout = audio_denoised[0].data.cpu().numpy()
                    #audioout = audio[0].data.cpu().numpy()
                    audioout32 = np.float32(audioout)
 
                    wav_name = 'wavs_out/' + str(self.file_count) + '.wav'
                    result.append([text, wav_name])
                    sf.write(wav_name, audioout32, 22050)
                    inferer.file_count += 1

                    # a = AudioSegment.from_file("out" + str(i) + ".wav") 
                    # t_play = threading.Thread(target=self.play, args=(a,))
                    # t_play.start()
                    # entry = np.array([text, wav_name])
                    # self.add_entry([entry])
                    # self.file_count += 1
                return result


def callback_open_model_taco(sender, app_data):
    path = app_data["file_path_name"]
    path = path.rstrip('.*')
    inferer.set_taco_model_path(path)

def callback_open_model_waveglow(sender, app_data):
    path = app_data["file_path_name"]
    path = path.rstrip('.*')
    inferer.set_waveglow_model_path(path)

def callback_open_model_hifigan(sender, app_data):
    path = app_data["file_path_name"]
    path = path.rstrip('.*')
    inferer.set_hifigan_model_path(path)

def callback_open_text_file(sender, app_data):
    d_path = app_data["selections"]
    key = list(d_path.keys())[0]
    path = app_data["selections"][key]
    inferer.set_text_file_path(path)

def callback_open_project(sender, app_data):
    path = app_data["file_path_name"]
    path = path.rstrip('.*')
    trainer.set_hifigan_project_name(path)

def callback_open_project_checkpoint(sender, app_data):
    path = app_data["file_path_name"]
    path = path.rstrip('.*')
    trainer.set_hifigan_checkpoint_name(path)


def callback_run_inference(sender, app_data, user_data):
    if user_data == "single": 
        t = dpg.get_value("text_input")
        if t:
            print("running inference")
            result = inferer.run_inference(t, "text_input", None)
            a = AudioSegment.from_file(result[0]) 
            t_play = threading.Thread(target=inferer.play, args=(a,))
            t_play.start()
            entry = np.array([t, result[0]])
            inferer.add_entry([entry])
            inferer.file_count += 1            
        else:
            print("Nothing to infer!")
            return
    
    elif user_data == "file":
        print(inferer.get_text_file_path())
        if inferer.get_text_file_path():
            if os.path.exists(inferer.get_text_file_path()):
                with open(inferer.get_text_file_path(), 'r') as f:
                    r = f.readlines()
                    text_file = " ".join(r)
                    print("opened text file.")
                    print("running inference")
                    result = inferer.run_inference(text_file, "text_input_file", None)
                    for r in result:
                        entry = np.array([r[0], r[1]])
                        inferer.add_entry([entry])
            else:
                #file not found
                print("Text file not found!")
                return



def callback_train_taco(sender, data):
    print("running taco training")
    trainer.train_taco()

def callback_train_hifigan(sender, data):
    if trainer.is_running():
        return
    print("running hifigan training")
    trainer.train_hifigan()

def callback_stop_training(sender, data):
    trainer.stop_training_hifigan()
    trainer.stop_training_tacotron2()
    trainer.stop_training_waveglow()

def callback_start_tensorboard(sender, data):
    path = trainer.get_hifigan_checkpoint_name()
    if not path:
        return
    import webbrowser as web
    web.open("http://localhost:6006")
    # out = "tensorboard --logdir '/model utilities/hifi-gan/attenborough.model/logs'"
    # print(out)
    tp = subprocess.Popen(['tensorboard', '--logdir', path])
    trainer.set_tensorboard_process(tp)

def callback_export_infer_table(sender, data):
    with open("wav_list.csv", 'w') as f:
        t = dpg.get_item_children("infer_table")
        for i in range(0, len(t[1])):
            f.write(dpg.get_value("wav_path_" + str(i)))
            f.write('|')
            f.write(dpg.get_value("input_text_" + str(i)))
            f.write('\n')

with dpg.window(tag='mainwindow', label="Model Utilites"):
   
    with dpg.tab_bar(tag="tab_bar_1"):        
        with dpg.tab(tag="setup_tab", label=" Setup and Config "):
            dpg.add_spacer(height=5)

            
        with dpg.tab(tag="inference_tab", label=" Run Inference "):
            with dpg.file_dialog(modal=True, width=800, directory_selector=False, show=False, callback=callback_open_model_taco, tag="open_model_taco"):
                dpg.add_file_extension(".*", color=(255, 255, 255, 255))

            with dpg.file_dialog(modal=True, width=800, directory_selector=False, show=False, callback=callback_open_model_waveglow, tag="open_model_waveglow"):
                dpg.add_file_extension(".*", color=(255, 255, 255, 255))

            with dpg.file_dialog(modal=True, width=800, directory_selector=False, show=False, callback=callback_open_model_hifigan, tag="open_model_hifigan"):
                dpg.add_file_extension(".*", color=(255, 255, 255, 255))

            with dpg.file_dialog(modal=True, width=800, directory_selector=False, show=False, callback=callback_open_text_file, tag="open_text_file"):
                dpg.add_file_extension(".*", color=(255, 255, 255, 255))

            with dpg.file_dialog(modal=True, width=800, directory_selector=True, show=False, callback=callback_open_project, tag="open_project_dialog"):
                dpg.add_file_extension(".*", color=(255, 255, 255, 255))                

            with dpg.file_dialog(modal=True, width=800, directory_selector=True, show=False, callback=callback_open_project_checkpoint, tag="open_project_checkpoint_dialog"):
                dpg.add_file_extension(".*", color=(255, 255, 255, 255))   

            dpg.add_spacer(height=5)
            dpg.add_text("Produce audio from nvidia tacotron2 model:")
            dpg.add_spacer(height=5)
            dpg.add_button(label="Choose Tacotron2 model", tag="choose_model_taco", callback=lambda: dpg.show_item("open_model_taco"))
            dpg.add_text("", tag="tacotron2_model_status")
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Choose Hifi-Gan model", tag="choose_model_hifigan", callback=lambda: dpg.show_item("open_model_hifigan"))  
                dpg.add_text("", tag="hifigan_model_status")            
                dpg.add_text("Or")       
                dpg.add_button(label="Choose Waveglow model", tag="choose_model_waveglow", callback=lambda: dpg.show_item("open_model_waveglow"))
                dpg.add_text("", tag="waveglow_model_status")                 
            dpg.add_spacer(height=5)   
            dpg.add_text("Input text:")
            with dpg.group(horizontal=True):             
                dpg.add_input_text(width=800, tag="text_input")
                dpg.add_button(label="Run inference", tag="run_inference_single", callback=callback_run_inference, user_data="single")
            dpg.add_spacer(height=5)   
            with dpg.group(horizontal=True):              
               dpg.add_button(label="Choose text file", tag="choose_text_file", callback=lambda: dpg.show_item("open_text_file"))
               dpg.add_button(label="Run inference", tag="run_inference", callback=callback_run_inference, user_data="file")
               dpg.add_button(label="Export .csv", tag="export_infer_table", callback=callback_export_infer_table)

            dpg.add_spacer(height=5)
            

        # with dpg.tab(tag="train_tacotron2_tab", label=" Train Tacotron2 "):
        #     dpg.add_spacer()    
        #     dpg.add_button(label="Train Tacotron2 model", tag="train_taco")
        #     dpg.add_clicked_handler("train_taco", callback=callback_train_taco)
        #     dpg.add_spacer()    
        #     dpg.add_button(label="Stop training", tag="stop_training_tacotron2")
        #     dpg.add_clicked_handler("stop_training_tacotron2", callback=callback_stop_training)       
        #     dpg.add_spacer()    
        #     dpg.add_text("Shell output displayed here", tag="shell_output_tacotron2")      

        with dpg.tab(tag="train_hifigan_tab", label=" Train Hifi-Gan "):  
            dpg.add_spacer()    
            dpg.add_text("Project folder should contain audio clips in its /wavs directory.\nTraining file should be named 'training.csv' and validation file named 'validation.csv'")
            dpg.add_spacer()                
            dpg.add_button(label="Choose project folder", tag="open_project", callback=lambda: dpg.show_item("open_project_dialog"))
            dpg.add_spacer()                
            dpg.add_button(label="Choose checkpoint folder (none for new)", tag="open_project_checkpoint", callback=lambda: dpg.show_item("open_project_checkpoint_dialog"))
            dpg.add_spacer()    
            dpg.add_button(label="Train HifiGan model", tag="train_hifigan", callback=callback_train_hifigan)
            dpg.add_spacer()    
            dpg.add_button(label="Stop training", tag="stop_training_hifigan", callback=callback_stop_training)
            dpg.add_spacer()    
            dpg.add_button(label="Start Tensorboard", tag="start_tensorboard", callback=callback_start_tensorboard)
            dpg.add_spacer()    
            dpg.add_text("Shell output displayed here", tag="shell_output_hifigan")  

        # with dpg.tab(tag="train_waveglow_tab", label=" Train Waveglow "):        
        #     dpg.add_spacer()    
        #     dpg.add_button(label="Stop training", tag="stop_training_waveglow")
        #     dpg.add_clicked_handler("stop_training_waveglow", callback=callback_stop_training)       
        #     dpg.add_spacer()    
        #     dpg.add_text("Shell output displayed here", tag="shell_output_waveglow")

inferer = Inferer()
trainer = Trainer()
   
with dpg.font_registry():
    dpg.add_font("CheyenneSans-Light.otf", 20)

dpg.bind_item_font("tab_bar_1", "CheyenneSans-Light.otf")

dpg.create_viewport(title="Deep Voice Model Utilities v1.0 by YouMeBangBang", width=1200, height=800)

dpg.setup_dearpygui()
dpg.show_viewport()

dpg.set_global_font_scale(1.3)
dpg.set_primary_window("mainwindow", True)


dpg.start_dearpygui()


dpg.destroy_context()

