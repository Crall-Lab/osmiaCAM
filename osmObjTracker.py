import cv2

def main(video_path, min_size, max_size, intensity_threshold, start_frame=0):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Could not open video file.")
        return
	
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print('Total frames in video:', total_frames)
	
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    ret, prev_frame = cap.read()
    if not ret:
        print("Error: Could not read video frame.")
        return

    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("End of video.")
            break

        frame_count += 1
        if frame_count % 50 != 0:  # Process every 50th frame
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame_diff = cv2.absdiff(gray, prev_gray)
        _, thresh = cv2.threshold(frame_diff, intensity_threshold, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            if min_size < area < max_size:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.drawContours(frame, [contour], 0, (0, 0, 255), 2)

        cv2.imshow('Motion Capture', frame)
        prev_gray = gray

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    video_path = "/Users/jamescrall/Dropbox/Work/_Research/osmia/output_video.mp4"
    min_size = 200  # adjust as needed
    max_size = 10000  # adjust as needed
    intensity_threshold = 15  # adjust as needed
    start_frame = 0  # adjust as needed
    main(video_path, min_size, max_size, intensity_threshold, start_frame)
