import cv2

def play_video_auto(video_path):
    """ Plays an MP4 video with automatic playback and frame number in title """

    video_capture = cv2.VideoCapture(video_path)

    if not video_capture.isOpened():
        print("Error: Unable to open video file")
        return

    total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
    current_frame = 0

    cv2.namedWindow('Video', cv2.WINDOW_NORMAL)

    while True:
        ret, frame = video_capture.read()
        
        if not ret:
            print("End of video")
            break

        # Update frame number in window title
        cv2.setWindowTitle('Video', f"Frame {current_frame}/{total_frames}")

        cv2.imshow('Video', frame)
        current_frame += 1

        # Adjust playback speed (waitKey controls frame delay in milliseconds)
        if cv2.waitKey(30) & 0xFF == ord('q'):  # Press 'q' to exit
            break

    video_capture.release()
    cv2.destroyAllWindows()

# Get video file path from user
video_path = input("Enter the MP4 file path: ")
play_video_auto(video_path)
