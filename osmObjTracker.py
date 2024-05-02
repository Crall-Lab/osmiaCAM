import cv2
import numpy as np

def main(video_path, min_size, max_size, intensity_threshold, start_frame=0):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Could not open video file.")
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print('Total frames in video:', total_frames)

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    # Parameters for running background estimation
    background_subsampling = 5
    background_history = 50
    background_buffer = []

    # Initialize the background buffer with the first frame
    for _ in range(background_history):
        ret, frame = cap.read()
        if not ret:
            print("Error: Could not read video frame.")
            return
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        background_buffer.append(gray_frame)

    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("End of video.")
            break

        frame_count += 1
        if frame_count % 20 != 0:  # Process every 20th frame
            continue

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Update the background buffer with the current frame
        if len(background_buffer) < background_history:
            background_buffer.append(gray_frame)
        else:
            background_buffer.pop(0)
            background_buffer.append(gray_frame)

        # Subsample frames for background estimation
        if len(background_buffer) >= background_history and len(background_buffer) % background_subsampling == 0:
            background = np.median(background_buffer, axis=0).astype(np.uint8)
            prev_gray = background
        else:
            prev_gray = background_buffer[-1]

        frame_diff = cv2.absdiff(gray_frame, prev_gray)
        _, thresh = cv2.threshold(frame_diff, intensity_threshold, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            if min_size < area < max_size:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.drawContours(frame, [contour], 0, (0, 0, 255), 2)

        cv2.imshow('Motion Capture', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    video_path = "/Users/jamescrall/Dropbox/Work/_Research/osmia/output_video.mp4"
    min_size = 10  # adjust as needed
    max_size = 2000  # adjust as needed
    intensity_threshold = 15  # adjust as needed
    start_frame = 13000  # adjust as needed
    main(video_path, min_size, max_size, intensity_threshold, start_frame)
