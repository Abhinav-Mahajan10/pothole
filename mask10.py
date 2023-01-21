import cv2
import os
import numpy as np
import random
import colorsys
import argparse
import time
from mrcnn import model as modellib
from mrcnn import visualize
import matplotlib
from custom import CustomConfig
import tensorflow as tf
import time
from estimators import depth_estimator
from _3D_reconstruction import coordinates
from random import sample
import math

gpu = len(tf.config.list_physical_devices('GPU'))>0
print("GPU is", "available" if gpu else "NOT AVAILABLE")


# class MyConfig(CocoConfig):
#     NAME = "my_coco_inference"
#     # Set batch size to 1 since we'll be running inference on one image at a time.
#     # Batch size = GPU_COUNT * IMAGES_PER_GPU
#     GPU_COUNT = 1
#     IMAGES_PER_GPU = 24


def prepare_mrcnn_model(model_path, model_name, class_names, my_config):
    classes = open(class_names).read().strip().split("\n")
    print("No. of classes", len(classes))

    hsv = [(i / len(classes), 1, 1.0) for i in range(len(classes))]
    COLORS = list(map(lambda c: colorsys.hsv_to_rgb(*c), hsv))
    random.seed(42)
    random.shuffle(COLORS)

    #["mrcnn_class_logits", "mrcnn_bbox_fc", "mrcnn_bbox", "mrcnn_mask", "rpn_model"]
    model = modellib.MaskRCNN(mode="inference", model_dir=model_path, config=my_config)
    model.load_weights(model_name, by_name=True)

    return COLORS, model, classes


def perform_inference_image(image_path, model, colors, classes, draw_bbox, mrcnn_visualize, instance_segmentation,
                            save_enable):
    test_image = cv2.imread(image_path)
    test_image = cv2.cvtColor(test_image, cv2.COLOR_BGR2RGB)

    output = custom_visualize(test_image, model, colors, classes, draw_bbox, mrcnn_visualize, instance_segmentation, 0)
    if not mrcnn_visualize:
        if save_enable:
            cv2.imwrite("result.png", output)
        cv2.imshow("Output", output)
        cv2.waitKey()
        cv2.destroyAllWindows()


def custom_visualize(test_image, model, colors, classes, draw_bbox, mrcnn_visualize, instance_segmentation, frame_no):
    start = time.time()
    print(colors)
    detections = model.detect([test_image], verbose=1)[0]
    end = time.time()

    print("Time taken to detect: " +  str(end-start))

    if mrcnn_visualize:
        matplotlib.use('TkAgg')
        out = visualize.display_instances(test_image, detections['rois'], detections['masks'], detections['class_ids'],
                                    classes,
                                    detections['scores'])
        print("returning out")
        return out

    if instance_segmentation:
        hsv = [(i / len(detections['rois']), 1, 1.0) for i in range(len(detections['rois']))]
        colors = list(map(lambda c: colorsys.hsv_to_rgb(*c), hsv))
        random.seed(42)
        random.shuffle(colors)

    

    

    pothole_depths = []
    surface_areas = []
    severity_labels = []
    mask_colours = []
    #iterates over no of pothole   
    print("mask shapes")
    print(detections["masks"].shape)

    for i in range(0, detections["rois"].shape[0]):
        (startY, startX, endY, endX) = detections["rois"][i]
        bounding_box = []
        bb_endpoints = [[startX, startY], [endX, startY], [startX, endY], [endX, endY]]
        pothole_depth = 0
        classID = detections["class_ids"][i]

        mask = detections["masks"][:, :, i]
        pixel_arr = np.argwhere(mask == True)
        
        if instance_segmentation:
            color = colors[i][::-1]
        else:
            color = colors[classID][::-1]

        # To visualize the pixel-wise mask of the object
        
        depth_start = time.time()
        arr = np.argwhere(mask == -1)
        num_rows_in_sample = int(arr.shape[0] * sampling_rate)
        
        for point in arr[np.random.choice(arr.shape[0], num_rows_in_sample, replace=False)]:
            projection = coordinates.get_coordinate(frame_no, point[1], point[0])
            if projection is not None:
                print('pothole depth')
                print(arr.shape)
                pothole_depth = min(pothole_depth, projection[1])
                print(pothole_depth)
        
        ref_depth = depth_estimator.get_ref_depth(bounding_box, frame_no)
        
        
        per_area = pixel_arr.shape[0] * 100 / (mask.shape[0] * mask.shape[1])

        severity_label = 'HIGH'
        mask_colour = [255, 0, 0]
        if per_area > 3:
            severity_label = 'ROAD SECTION DAMAGED'
            mask_colour = [255, 0, 0]
        else:
            depth = -1
            if per_area <= 0.6:

                depth = -5 * per_area + 7
                
            elif per_area <= 1:
                depth = -5 * per_area + 8
                
            else:
                depth = -1 * per_area + 5
                

            print(depth, per_area)

            if (depth >= 5):
                severity_label = 'HIGH'
                mask_colour = [255, 0, 0]
            elif (depth >= 4):
                severity_label = 'MODERATE'
                mask_colour = [255,255,0]
            else:
                severity_label = 'LOW'
                mask_colour = [85, 107, 47]

        #(r, g, b) = mask_colour
        print(mask_colour)
        test_image = visualize.apply_mask(test_image, mask, mask_colour, alpha=0.5)

        
       
        pothole_depths.append(pothole_depth-ref_depth)
        surface_areas.append(pixel_arr.shape[0])
        severity_labels.append(severity_label)
        mask_colours.append(mask_colour)





        

    test_image = cv2.cvtColor(test_image, cv2.COLOR_RGB2BGR)
    print(mask_colours)

    if draw_bbox == True:
        #print("inside bboc")
        for i in range(0, len(detections["scores"])):
            (startY, startX, endY, endX) = detections["rois"][i]

            classID = detections["class_ids"][i]
            label = 'Severity'
            score = pothole_depths[i]
            final_color = mask_colours[i]
            final_color = [final_color[2], final_color[1], final_color[0]]
            severity_label = severity_labels[i]

            # if instance_segmentation:
            #     color = [int(c) for c in np.array(colors[i]) * 255]

            # else:
            #     color = [int(c) for c in np.array(colors[classID]) * 255]

            cv2.rectangle(test_image, (startX, startY), (endX, endY), final_color, 2)
            print("drawing box")
            print(final_color)
            text = "{}: {}".format(label, severity_label)
            y = startY - 10 if startY - 10 > 10 else startY + 10
            cv2.putText(test_image, text, (startX, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, final_color, 2)

    return test_image

def perform_inference_video(use_camera, video_path, model, colors, classes, draw_bbox, mrcnn_visualize,
                            instance_segmentation, save_enable):
    if use_camera:
        video = cv2.VideoCapture(0)
        time.sleep(2.0)
    else:
        video = cv2.VideoCapture(video_path)

    video_flag = True
    
    cnt = 0
    
    while True:
        ret, frame = video.read()

        cnt += 1

        if(cnt % 12 != 0):
            continue
        
        
        
        if save_enable and video_flag:
            out = cv2.VideoWriter("full_video_out4.mp4", cv2.VideoWriter_fourcc(*'MP4V'), 5,
                                  (frame.shape[1], frame.shape[0]))
            video_flag = False

        if not ret:
            break

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        output = custom_visualize(frame, model, colors, classes, draw_bbox, mrcnn_visualize, instance_segmentation, cnt)
        
        cv2.imshow("Output", output)

        if save_enable:
            out.write(output)
        
        

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break


    video.release()

class InferenceConfig(CustomConfig):
        GPU_COUNT = 1
        IMAGES_PER_GPU = 1


if __name__ == '__main__':

    sampling_rate = 0.01

    parser = argparse.ArgumentParser()
    parser.add_argument('--image', help='Path to the test images', default=None)
    parser.add_argument('--model_path', help='Path to the model directory', default='models/')
    parser.add_argument('--model_name', help='Name of the model file', default='models/mask_rcnn_model.h5')
    parser.add_argument('--class_names', help='Path to the class labels', default='pothole_classes.txt')
    parser.add_argument('--mrcnn_visualize', help='Use the built-in visualize method', type=bool, default=False)
    parser.add_argument('--instance_segmentation', help='To toggle between semantic and instance segmentation',
                        type=bool, default=True)
    parser.add_argument('--draw_bbox', help='Draw the bounding box with class labels', type=bool, default=True)
    parser.add_argument('--camera', help='Perform live detection', type=bool, default=False)
    parser.add_argument('--video', help='Path to video file', default=None)
    parser.add_argument('--save_enable', help='Enable to save processed image or video', type=bool, default=True)
    args = vars(parser.parse_args())

    if args['image']:
        my_config = InferenceConfig()
        my_config.display()
        colors, model, classes = prepare_mrcnn_model(args['model_path'], args['model_name'], args['class_names'],
                                                     my_config)
        perform_inference_image(args['image'], model, colors, classes, args['draw_bbox'], args['mrcnn_visualize'],
                                args['instance_segmentation'], args['save_enable'])

    if args['camera'] or args['video']:
        use_camera = args['camera']
        video_path = args['video']

        my_config = InferenceConfig()
        my_config.display()
        colors, model, classes = prepare_mrcnn_model(args['model_path'], args['model_name'], args['class_names'],
                                                     my_config)
        perform_inference_video(use_camera, video_path, model, colors, classes, args['draw_bbox'],
                                args['mrcnn_visualize'],
                                args['instance_segmentation'], args['save_enable'])
