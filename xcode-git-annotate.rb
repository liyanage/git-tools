#!/usr/bin/ruby -w

selection_start = %%%{PBXSelectionStart}%%%
line_start = 0
selection_line_number = 1
STDIN.each do |line|
	line_end = line_start + line.length
	line_range = line_start ... line_end
	break if line_range.include? selection_start
	line_start += line.length
	selection_line_number += 1
end

dir = File.dirname '%%%{PBXFilePath}%%%'
file = ENV['FILENAME']
Dir.chdir dir

output_line_number = 1
%x(git annotate '#{file}').each do |line|
	if output_line_number == selection_line_number
		print '%%%{PBXSelection}%%%'
		print line
		print '%%%{PBXSelection}%%%'
	else
		print line
	end
	output_line_number += 1
end

system %Q([ -e /opt/local/bin/detach ] && /opt/local/bin/detach osascript -e "delay 1.0\ntell application "'"Xcode"'"\nset selected paragraph range of source document 1 to {#{selection_line_number}, #{selection_line_number}}\nend tell")
