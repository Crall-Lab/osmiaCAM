import cv2

def play_video_frame_by_frame(video_path):
    """ Plays an MP4 video frame by frame with user control """
    
    video_capture = cv2.VideoCapture(video_path)

    if not video_capture.isOpened():
        print("Error: Unable to open video file")
        return

    total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
    current_frame = 0

    cv2.namedWindow('Video', cv2.WINDOW_NORMAL)

    while True:
        video_capture.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = video_capture.read()
        
        if not ret:
            print("End of video or error reading frame")
            break

        cv2.imshow('Video', frame)

        key = cv2.waitKey(0) & 0xFF  # Wait indefinitely for key press

        if key == ord('q'):  # Quit
            break
        elif key in [ord('n'), 83]:  # Next frame (→ or 'n')
            current_frame = min(current_frame + 1, total_frames - 1)
        elif key in [ord('p'), 81]:  # Previous frame (← or 'p')
            current_frame = max(current_frame - 1, 0)

    video_capture.release()
    cv2.destroyAllWindows()

# Get video file path from user
video_path = input("Enter the MP4 file path: ")
play_video_frame_by_frame(video_path)
