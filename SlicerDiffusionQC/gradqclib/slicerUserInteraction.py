import slicer
import vtk
import os
import sys

from diffusionqclib.dwi_attributes import dwi_attributes
from diffusionqclib.saveResults import saveResults

import numpy as np

FAIL= '\tFail' # \t is for visually separating fail gradients
UNSURE= '\tUnsure' # \t is for visually separating Unsure gradients

class slicerGUI():

  def slicerUserInterface(self, userDWIpath, userDWInode, label, summary,
                          discardButton, keepButton, sureButton, unsureButton, nextButton, resetButton, saveButton):

    self.dwiPath= userDWIpath
    self.prefix = os.path.basename(self.dwiPath.split('.')[0])
    self.directory = os.path.dirname(os.path.abspath(self.dwiPath))
    self.deletion= np.load(os.path.join(self.directory, self.prefix+'_QC.npy'))
    self.confidence= np.load(os.path.join(self.directory, self.prefix+'_confidence.npy'))
    self.KLdiv= np.load(os.path.join(self.directory, self.prefix+'_KLdiv.npy'))

    self.qualityBackUp= self.deletion.copy()
    self.confidenceBackUp= self.confidence.copy()
    self.dwiNode= userDWInode
    self.decisionLabel= label
    self.summaryLabel= summary

    # Write out algorithm summary
    self.summaryUpdate()

    # The following code is for making a table
    # Create table with gradient index, decision, and confidence
    self.tableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode")
    table = self.tableNode.GetTable()

    arrX= vtk.vtkStringArray( )
    arrX.SetName("Gradient #")
    table.AddColumn(arrX)

    arrY1 = vtk.vtkStringArray()
    arrY1.SetName("Decision")
    table.AddColumn(arrY1)

    arrY2 = vtk.vtkStringArray()
    arrY2.SetName("Confidence")
    table.AddColumn(arrY2)

    arrY3 = vtk.vtkStringArray()
    arrY3.SetName("Marked for deletion")
    table.AddColumn(arrY3)

    table.SetNumberOfRows(self.KLdiv.shape[0])
    for i in range(self.KLdiv.shape[0]):

      # To prevent the gradient index confuse with row number '{:10}'.format(i)
      table.SetValue(i, 0, '{:10}'.format(i))
      table.SetValue(i, 1, 'Pass' if self.deletion[i] else FAIL)
      table.SetValue(i, 2, 'Sure' if self.confidence[i] else UNSURE)
      table.SetValue(i, 3, 'X' if not self.deletion[i] else ' ')

    currentLayout = slicer.app.layoutManager().layout
    layoutWithTable = slicer.modules.tables.logic().GetLayoutWithTable(currentLayout)
    slicer.app.layoutManager().setLayout(layoutWithTable)
    slicer.app.applicationLogic().GetSelectionNode().SetReferenceActiveTableID(self.tableNode.GetID())
    slicer.app.applicationLogic().PropagateTableSelection()

    # Table display finished --------------------------------------------------------------------



    # The following code is for making graph
    self.graphTableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode")
    graphTable = self.graphTableNode.GetTable()

    arrX = vtk.vtkIntArray()
    arrX.SetName("Slice #")
    graphTable.AddColumn(arrX)

    arrY1 = vtk.vtkFloatArray()
    arrY1.SetName("Divergence")
    graphTable.AddColumn(arrY1)

    graphTable.SetNumberOfRows(self.KLdiv.shape[1])


    # Create a plot series nodes
    plotSeriesNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotSeriesNode", "KL div")
    plotSeriesNode.SetAndObserveTableNodeID(self.graphTableNode.GetID())
    plotSeriesNode.SetXColumnName("Slice #")
    plotSeriesNode.SetYColumnName("Divergence")
    plotSeriesNode.SetPlotType(slicer.vtkMRMLPlotSeriesNode.PlotTypeScatter)
    plotSeriesNode.SetLineStyle(slicer.vtkMRMLPlotSeriesNode.LineStyleSolid)
    plotSeriesNode.SetMarkerStyle(slicer.vtkMRMLPlotSeriesNode.MarkerStyleSquare)
    plotSeriesNode.SetUniqueColor()

    # Create plot chart node
    plotChartNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotChartNode")
    plotChartNode.AddAndObservePlotSeriesNodeID(plotSeriesNode.GetID())
    plotChartNode.SetTitle('KL divergence value plot')
    plotChartNode.SetXAxisTitle('Slice index')
    plotChartNode.SetYAxisTitle('KL div')


    # Switch to a layout that contains a plot view to create a plot widget
    layoutManager = slicer.app.layoutManager()
    layoutWithPlot = slicer.modules.plots.logic().GetLayoutWithPlot(layoutManager.layout)
    layoutManager.setLayout(layoutWithPlot)

    # Properly set the plot chart interaction mode

    # Select chart in plot view
    plotWidget = layoutManager.plotWidget(0)
    plotViewNode = plotWidget.mrmlPlotViewNode()
    plotViewNode.SetPlotChartNodeID(plotChartNode.GetID())
    plotViewNode.SetInteractionMode(plotViewNode.InteractionModeSelectPoints) # select points mode

    # Graph display finished -------------------------------------------------------------

    mainwindow = slicer.util.mainWindow()
    self.figureHandle= slicer.util.findChildren(mainwindow, className="qMRMLPlotView")[0]
    self.tableHandle = slicer.util.findChildren(mainwindow, className="qMRMLTableView")[0]

    self.tableHandle.connect('selectionChanged()', self.gradientUpdate)
    self.figureHandle.connect('dataSelected(vtkStringArray*, vtkCollection*)', self.sliceUpdate)
    discardButton.connect('clicked(bool)', self.discardGradient)
    keepButton.connect('clicked(bool)', self.keepGradient)
    nextButton.connect('clicked(bool)', self.nextReview)
    sureButton.connect('clicked(bool)', self.makeSure)
    unsureButton.connect('clicked(bool)', self.makeUnsure)
    saveButton.connect('clicked(bool)', self.finishInteraction)
    resetButton.connect('clicked(bool)', self.resetResults)

    # TODO: Use the above handles to disconnect all signals after 'Save' (not much necessary)

    # Displaying 0th gradient graph as default
    self.plotUpdate(0)


  def finishInteraction(self):
    # Return only if pushbutton save is pressed
    hdr, mri, grad_axis, _, _, _ = dwi_attributes(self.dwiPath)
    saveResults(self.prefix, self.directory, self.deletion, None, None, hdr, mri, grad_axis, True)



  # Getting specific point ID from graph
  # Switching among slices
  def sliceUpdate(self,_,dataPointID):

    res = self.dwiNode.GetSpacing()[2]  # The 2 corresponds to axial view (check if we need to soft code)
    org = self.dwiNode.GetOrigin()[2]  # The 2 corresponds to axial view (check if we need to soft code)
    axialView = slicer.util.getNode('vtkMRMLSliceNodeRed')

    if not dataPointID.GetNumberOfItems( ):
      # if no point is selected, do nothing
      return
    else:
      array= dataPointID.GetItemAsObject(0)
      slice_index = array.GetValue(0)

      # The following lines set appropriate slice in the axial view only
      if slice_index<= abs(org)/2:
        offset= res*slice_index+org-1
      else:
        offset= res*slice_index+org

      axialView.SetSliceOffset(offset)

  def discardGradient(self):

      arr = self.dwiNode.GetDiffusionWeightedVolumeDisplayNode()
      # Mark the corresponding gradient as fail
      diffusion_index= arr.GetDiffusionComponent()
      self.deletion[diffusion_index]= 0 # bad ones are marked with 0

      table = self.tableNode.GetTable()
      table.SetValue(diffusion_index, 1, FAIL)
      table.SetValue(diffusion_index, 3, 'X')
      self.tableNode.Modified()

      self.summaryUpdate()

  def keepGradient(self):

      arr = self.dwiNode.GetDiffusionWeightedVolumeDisplayNode()
      # Mark the corresponding gradient for self.deletion
      diffusion_index= arr.GetDiffusionComponent()
      self.deletion[diffusion_index]= 1 # good ones are marked with 1

      table = self.tableNode.GetTable()
      table.SetValue(diffusion_index, 1, 'Pass')
      table.SetValue(diffusion_index, 3, ' ')
      self.tableNode.Modified()

      self.summaryUpdate()

  def makeUnsure(self):

      arr = self.dwiNode.GetDiffusionWeightedVolumeDisplayNode()
      # Mark the corresponding gradient as fail
      diffusion_index= arr.GetDiffusionComponent()
      self.confidence[diffusion_index]= 0 # unsure ones are marked with 0

      table = self.tableNode.GetTable()
      table.SetValue(diffusion_index, 2, UNSURE)
      self.tableNode.Modified()

      self.summaryUpdate()

  def makeSure(self):

      arr = self.dwiNode.GetDiffusionWeightedVolumeDisplayNode()
      # Mark the corresponding gradient for self.deletion
      diffusion_index= arr.GetDiffusionComponent()
      self.confidence[diffusion_index]= 1 # sure ones are marked with 1

      table = self.tableNode.GetTable()
      table.SetValue(diffusion_index, 2, 'Sure')
      self.tableNode.Modified()

      self.summaryUpdate()


  # Getting specific point ID from table
  # Switching among gradients
  def gradientUpdate(self):

      index = self.tableHandle.selectedIndexes()[0]
      diffusion_index = index.row( )-1


      # Probable BUG: every time selectionChanged(), gradientUpdate() is called twice
      # That means all the work below are done twice for no reason
      # The following print statement is for debugging
      # print("Index ", diffusion_index)


      # The following line sets appropriate gradient
      if diffusion_index >= 0:
        self.plotUpdate(diffusion_index) # Label update is done inside this function

  def plotUpdate(self, diffusion_index):

      # Select corresponding row of the table
      self.tableHandle.selectRow(diffusion_index+1)

      # Label update is done below
      arr = self.dwiNode.GetDiffusionWeightedVolumeDisplayNode()
      arr.SetDiffusionComponent(diffusion_index)

      q= 'Pass' if self.deletion[diffusion_index] else FAIL
      c= 'Sure' if self.confidence[diffusion_index] else UNSURE
      self.decisionLabel.setText("Displaying gradient # "+str(diffusion_index)+' ,\t'+
                    "Quality: "+ q +' ,\t'+ "Confidence: "+ c)

      # The following code is for making a plot
      # Create table with slice index, and divergence value
      graphTable = self.graphTableNode.GetTable()

      for i in range(self.KLdiv.shape[1]):
        # Filling up row wise
        graphTable.SetValue(i, 0, i)
        graphTable.SetValue(i, 1, self.KLdiv[diffusion_index, i])

      self.graphTableNode.Modified()

  def resetResults(self):

    table = self.tableNode.GetTable()

    for i in range(self.KLdiv.shape[0]):

      table.SetValue(i, 0, i)
      table.SetValue(i, 1, 'Pass' if self.qualityBackUp[i] else FAIL)
      table.SetValue(i, 2, 'Sure' if self.confidenceBackUp[i] else UNSURE)
      table.SetValue(i, 3, 'X' if not self.qualityBackUp[i] else ' ')

    self.tableNode.Modified()
    self.deletion= self.qualityBackUp.copy()
    self.plotUpdate(0)
    self.summaryUpdate()

  def nextReview(self):

    arr = self.dwiNode.GetDiffusionWeightedVolumeDisplayNode()

    diffusion_index = arr.GetDiffusionComponent()

    if (self.confidence==0).any( ):
       if diffusion_index<len(self.confidence)-1:
           i=diffusion_index+1
       else:
           i=0 # force to start from beginning

       while self.confidence[i]: # While sure, continue looping for the next unsure
           i+=1

       if i!=diffusion_index:
        arr.SetDiffusionComponent(i)
        self.plotUpdate(i)

  def summaryUpdate(self):
    self.summaryLabel.setText("Total gradients "+str(len(self.deletion))+
                              ",\t\t# of fails "+ str(len(np.where(self.deletion==0)[0]))+
                              ",\t# of unsures " + str(len(np.where(self.confidence == 0)[0])))