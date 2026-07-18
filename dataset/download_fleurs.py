import os
import shutil
import csv
import sys
import certifi
import requests
import tarfile
from tqdm import tqdm

def main():
    subsets = ["en_us", "hi_in", "ar_eg"]
    main_dataset_dir = "fleurs_dataset"
    
    print(f"Creating main dataset folder: {main_dataset_dir}")
    os.makedirs(main_dataset_dir, exist_ok=True)
    
    for subset in subsets:
        print(f"\n--- Processing subset: {subset} ---")
        subset_dir = os.path.join(main_dataset_dir, subset)
        os.makedirs(subset_dir, exist_ok=True)
        
        # 1. Download and parse the TSV metadata
        tsv_url = f"https://huggingface.co/datasets/google/fleurs/resolve/main/data/{subset}/train.tsv"
        print(f"Downloading TSV metadata from: {tsv_url}")
        try:
            tsv_response = requests.get(tsv_url, verify=certifi.where())
            tsv_response.raise_for_status()
        except Exception as e:
            print(f"Error fetching TSV metadata for {subset}: {e}")
            continue
            
        transcriptions_dict = {}
        for line in tsv_response.text.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) > 2:
                filename = parts[1].strip()
                transcription = parts[2].strip()
                transcriptions_dict[filename] = transcription
                
        print(f"Loaded {len(transcriptions_dict)} metadata records.")
        
        # 2. Stream the tar.gz archive and extract the first 5 wav samples
        tar_url = f"https://huggingface.co/datasets/google/fleurs/resolve/main/data/{subset}/audio/train.tar.gz"
        print(f"Streaming audio archive from: {tar_url}")
        
        try:
            # We use stream=True so the response bytes are read on demand
            response = requests.get(tar_url, stream=True, verify=certifi.where())
            response.raise_for_status()
            
            # Wrap the stream in tarfile with r|gz mode for sequential streaming
            tar = tarfile.open(fileobj=response.raw, mode="r|gz")
            
            transcriptions = []
            count = 0
            
            pbar = tqdm(total=5, desc=f"Extracting {subset} samples")
            for member in tar:
                if member.isfile() and member.name.endswith(".wav"):
                    filename = os.path.basename(member.name)
                    if filename in transcriptions_dict:
                        count += 1
                        
                        audio_filename = f"sample_{count}.wav"
                        txt_filename = f"sample_{count}.txt"
                        
                        audio_filepath = os.path.join(subset_dir, audio_filename)
                        txt_filepath = os.path.join(subset_dir, txt_filename)
                        
                        # Extract the file data block and write it to disk
                        f_in = tar.extractfile(member)
                        if f_in is not None:
                            with open(audio_filepath, "wb") as f_out:
                                shutil.copyfileobj(f_in, f_out)
                                
                            # Get the transcription text
                            transcription_text = transcriptions_dict[filename]
                            
                            # Save the individual transcription txt file
                            with open(txt_filepath, "w", encoding="utf-8") as f_txt:
                                f_txt.write(transcription_text)
                                
                            # Record metadata
                            transcriptions.append({
                                "filename": audio_filename,
                                "transcription": transcription_text
                            })
                            
                            pbar.update(1)
                            
                        if count >= 5:
                            break
            
            pbar.close()
            # Explicitly close the tar file and the network connection
            tar.close()
            response.close()
            
            # 3. Write summary transcriptions.csv
            csv_filepath = os.path.join(subset_dir, "transcriptions.csv")
            print(f"Writing CSV metadata file: {csv_filepath}")
            with open(csv_filepath, "w", encoding="utf-8", newline="") as f_csv:
                writer = csv.DictWriter(f_csv, fieldnames=["filename", "transcription"])
                writer.writeheader()
                writer.writerows(transcriptions)
                
            print(f"Successfully processed {count} samples for {subset}.")
            
        except Exception as e:
            print(f"Error processing audio stream for {subset}: {e}")

if __name__ == "__main__":
    main()
