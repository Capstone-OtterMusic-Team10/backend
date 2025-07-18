import sys
import os
import demucs.separate

def separate_audio(input_file, output_dir):

    # Separates an audio file into its constituent stems using the correct (musical) Demucs model.

    if not os.path.exists(input_file):
        print(f"Error: Input file not found at {input_file}", file=sys.stderr)
        sys.exit(1)  # Exit with an error code

    print(f"Starting Demucs separation for: {input_file}")

    # Run the separation using a high-quality model, saving as MP3
    demucs.separate.main([
        "-n", "htdemucs_ft",
        "-o", output_dir,
        "--mp3",
        "--mp3-bitrate", "320",
        input_file
    ])

    print("Demucs separation complete.")


# run script from the command line
if __name__ == '__main__':
    # Expects two command line arguments, the input file and the output directory
    if len(sys.argv) != 3:
        print("Usage: python separator.py <input_file_path> <output_directory_path>", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    separate_audio(input_path, output_path)
