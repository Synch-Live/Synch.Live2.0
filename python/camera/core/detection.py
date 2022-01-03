import cv2
import datetime
import imutils
import logging
import numpy as np
import sys

from typing import Any, List, Tuple, Optional, Union

# initialise logging to file
import camera.core.logger

# defaults to bright green
MIN_DETECT_HSV = np.array([ 50, 100, 140], np.uint8)
MAX_DETECT_HSV = np.array([ 85, 255, 255], np.uint8)
MIN_DETECT_CONTOUR = 100
MAX_DETECT_CONTOUR = 400


def log_detected(boxes: List[Tuple[int, int, int, int]]) -> None:
    """
    Write detected boxes to logfile

    Side-effects
    ------
    Write to logfile
    """
    for i, box in enumerate(boxes):
        logging.info(f'{i+1}, {box}')

    logging.info(f"Found {len(boxes)} blobs in frame.")


def draw_bbox(
        frame:  np.ndarray,
        player: int,
        rect:   Tuple[int, int, int, int]
    ) -> np.ndarray:
    """
    Draws bounding box of tracked object and object name on the frame

    Params
    ------
    frame
        a single frame of a cv2.VideoCapture()
    player
        the number identifying the current object being tracked
    rect
        a 4-element tuple with the coordinates and size of a rectangle
        ( x, y, width, height )

    Returns
    ------
        updated frame
    """
    (x, y, w, h) = rect
    frame = cv2.rectangle(frame, (x, y, w, h), (0, 255, 0), 2)

    frame = cv2.putText(frame, f"Player{player}", (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5, (0, 255, 0))

    return frame


def draw_annotations(
        frame: np.ndarray, boxes: List[Tuple[int, int, int, int]]
    ) -> np.ndarray:
    """
    Draws all necessary annotations (timestamp, tracked objects)
    onto the given frame

    Params
    ------
    frame
        a single frame of a cv2.VideoCapture() or picamera stream
    boxes
        a list of 4-element tuples with the coordinates and size
        of rectangles ( x, y, width, height )

    Returns
    -----
        updated frame
    """
    timestamp = datetime.datetime.now()
    frame = cv2.putText(frame, timestamp.strftime("%y-%m-%d %H:%M:%S"),
                (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (255, 255, 255), 1)

    for i, box in enumerate(boxes):
        # draw rectangle and label over the objects position in the video
        frame = draw_bbox(frame, i + 1, tuple([int(x) for x in box]))

    return frame


def detect_blobs(
        frame: np.ndarray,
        min_area: int = MIN_DETECT_CONTOUR,
        max_area: int = MAX_DETECT_CONTOUR
    ) -> List[cv2.KeyPoint]:
    """
    Gets the initial regions of interest (ROIs) to be tracked, which are green
    LEDs in a dark image. Use blob detection to extract circular convex regions
    of a certain area and bright colour

    TODO: bug in OpenCV2 does not allow me to change blob colour

    Params
    ------
    frame
        a single frame of a cv2.VideoCapture() or picamera stream
    min_area, max_area
        minimum and maximum area a blob requires to be detected

    Returns
    ------
        keypoints for each blob, consisting of centre of mass and radius of
        detected blobs
    """
    # invert frame as the detector is preset on dark colours
    inv_frame = cv2.bitwise_not(frame)

    # initialise detector params so only circular dark objects get selected
    # with an area within our bounds
    params = cv2.SimpleBlobDetector_Params()
    params.filterByCircularity = 1
    params.minCircularity = 0.9
    params.filterByArea = 1
    params.minArea = min_area
    params.maxArea = max_area
    params.filterByColor = 1
    params.blobColor = 0
    detector = cv2.SimpleBlobDetector_create(params)

    blobs = detector.detect(inv_frame)

    #frame_annot = cv2.drawKeypoints(frame, blobs, np.array([]), (0,255,0), cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)

    bboxes = [ cv2.boundingRect(blob) for blob in blobs ]

    return bboxes


def detect_colour(
        frame: np.ndarray,
        min_hsv: np.ndarray = MIN_DETECT_HSV,
        max_hsv: np.ndarray = MAX_DETECT_HSV,
        min_contour: int    = MIN_DETECT_CONTOUR,
        max_contour: int    = MAX_DETECT_CONTOUR,
        dump: bool          = False
    ) -> List[Tuple[int, int, int, int]]:
    """
    Gets the initial regions of interest (ROIs) to be tracked, which are green
    LEDs in a dark image. Uses a conversion to hue-saturation-luminosity to pick
    out the green objects in the image, and a dilation filter to emphasise the
    point-sized ROIs into bigger objects.

    Params
    ------
    frame
        a single frame of a cv2.VideoCapture() or picamera stream
    min_contour, max_contour
        minimum and maximum perimeter a rectangle requires to be detected
    min_hsv, max_hsv
        numpy arrays of shape (3,) where the elements represent HSV values to
        be used as colour range for the objects to be detected

    Returns
    ------
        a list of tuples, with the coordinates of the bounding boxes of the
        detected objects

    Side-effects
    ------
        centre of mass coordinates are logged for the detected boxes
    """
    # Convert the frame in RGB color space to HSV
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # create image mask by selecting the range of green hues from the HSV image
    green_mask = cv2.inRange(hsv_frame, min_hsv, max_hsv)

    if dump:
        cv2.imwrite('hsv_frame.jpg', hsv_frame)
        cv2.imwrite('green_mask.jpg', green_mask)

    # we look for punctiform green objects, so perform image dilation on mask
    # to emphasise these points
    kernel = np.ones((5, 5), "uint8")
    green_mask = cv2.dilate(green_mask, kernel)
    if dump:
        cv2.imwrite('green_mask_dilated.jpg', green_mask)

    res = cv2.bitwise_and(frame, frame, mask = green_mask)
    if dump:
        cv2.imwrite('img_masked.jpg', res)
    res = cv2.cvtColor(res, cv2.COLOR_BGR2GRAY)

    # Find the contours of all green objects
    contours, hierarchy = cv2.findContours(res,
        cv2.RETR_TREE,
        cv2.CHAIN_APPROX_SIMPLE)

    bboxes = []
    # go through detected contours and reject if not the wrong size or shape
    for i, contour in enumerate(contours):
        box = cv2.contourArea(contour)
        if(box >= min_contour and box <= max_contour):
            x, y, w, h = cv2.boundingRect(contour)

            if (w / h >= 0.8 or w / h <= 1.2):
                bboxes.append((x, y, w, h))

    log_detected(bboxes)

    return bboxes