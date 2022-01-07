import multiprocessing
import subprocess
import filecmp
import shutil
import hashlib
import logging
import i3ipc

import paths
from output import Output


def genBlurredImage(inputPath: str, outputPath: str, blurLevel: int) -> None:
    try:
        subprocess.run(['convert', inputPath, '-blur', '0x%d' % blurLevel, outputPath])
    except FileNotFoundError:
        logging.error('Could not create blurred version of wallpaper, ensure imagemagick is installed')
        exit()

    logging.info('Generated image %s' % outputPath)


def verifyWallpaperCache(wallpaperPath: str, wallpaperHash: str) -> bool:
    cachedWallpaper = paths.cachedImagePath(wallpaperPath, wallpaperHash)

    if paths.exists(cachedWallpaper) and filecmp.cmp(wallpaperPath, cachedWallpaper):
        logging.info('wallpaper %s is cached as %s' % (wallpaperPath, cachedWallpaper))
        return True

    logging.info('wallpaper %s added to the cache as %s' % (wallpaperPath, cachedWallpaper))
    shutil.copy(wallpaperPath, cachedWallpaper)
    return False


class BlurManager:
    def __init__(self, outputConfigs: dict, blurStrength: int, animationDuration: int) -> None:
        self.SWAY = i3ipc.Connection()
        self.outputs = {}

        animationFrames = [
            (i + 1) * (blurStrength // animationDuration) for i in range(animationDuration)
        ]

        # create an output object for each output in the configuration
        for name in outputConfigs:
            outputCfg = outputConfigs[name]
            # if output has no wallpaper set, no object needs to be made
            if not outputCfg['image']:
                logging.info('Output %s has no wallpaper set' % name)
                continue

            imageHash = hashlib.md5(outputCfg['image'].encode()).hexdigest()
            cachedImage = paths.cachedImagePath(outputCfg['image'], imageHash)

            self.outputs[name] = Output(
                name,
                cachedImage,
                [paths.framePath(imageHash, frame) for frame in animationFrames],
                {
                    'filter': outputCfg['filter'] ,
                    'anchor': outputCfg['anchor'],
                    'scaling-mode': outputCfg['scaling-mode'],
                }
            )

            # check if new wallpaper must be generated
            if not verifyWallpaperCache(outputCfg['image'], imageHash):
                print('Generating blurred wallpaper frames')
                print('This may take a minute...')
                with multiprocessing.Pool() as pool:
                    pool.starmap(
                        genBlurredImage,
                        [[cachedImage, paths.framePath(imageHash, frame), frame] for frame in animationFrames]
                    )
                print('Blurred wallpaper generated for %s' % name)
            else:
                print('Blurred wallpaper exists for %s' % name)


    def start(self) -> None:
        print("Listening...")
        self.SWAY.on(i3ipc.Event.WINDOW_NEW, self.handleBlur)
        self.SWAY.on(i3ipc.Event.WINDOW_CLOSE, self.handleBlur)
        self.SWAY.on(i3ipc.Event.WINDOW_MOVE, self.handleBlur)
        self.SWAY.on(i3ipc.Event.WORKSPACE_FOCUS, self.handleBlur)
        self.SWAY.main()


    def handleBlur(self, _sway: i3ipc.Connection, _event: i3ipc.Event) -> None:
        focusedWindow = self.SWAY.get_tree().find_focused()
        focusedWorkspace = focusedWindow.workspace()
        focusedOutputName = focusedWorkspace.ipc_data['output']

        try:
            if focusedWindow == focusedWorkspace: # if workspace is empty
                self.outputs[focusedOutputName].unblur()
            else:
                self.outputs[focusedOutputName].blur()
        except KeyError:
            logging.info('Output %s is not an Output object' % focusedOutputName)
            pass
