import cv2

def play_video(video_path):
    # Open the video file
    video_capture = cv2.VideoCapture(video_path)

    # Check if the video file opened successfully
    if not video_capture.isOpened():
        print("Error: Unable to open video file")
        return

    # Read the first frame
    ret, frame = video_capture.read()

    # Check if the first frame was read successfully
    if not ret:
        print("Error: Unable to read first frame")
        return

    # Create a window to display the video
    cv2.namedWindow('Video', cv2.WINDOW_NORMAL)

    while True:
        # Display the current frame
        cv2.imshow('Video', frame)

        # Wait for a key press; exit if 'q' is pressed
        key = cv2.waitKey(30)
        if key & 0xFF == ord('q'):
            break

        # Read the next frame
        ret, frame = video_capture.read()

        # Check if the frame was read successfully
        if not ret:
            print("End of video")
            break

    # Release the video capture object and close the window
    video_capture.release()
    cv2.destroyAllWindows()

# Replace 'video_path' with the path to your h264 video file
video_path = '/Users/jamescrall/Downloads/2024-05-01_00-40-02.h264'
play_video(video_path)
